"""
主评估脚本: 跑 testset 中的所有用例, 输出评估报告。

用法:
    # 仅跑检索端评估(不调用 LLM,快)
    python -m src.eval.run_eval --retrieval-only

    # 完整评估(含生成端,会调用 LLM)
    python -m src.eval.run_eval

    # 只跑指定画像
    python -m src.eval.run_eval --persona 张女士
"""

import argparse
import json
import logging
import time
from pathlib import Path

from src.pipeline.rag_pipeline import RAGPipeline
from src.eval.testset import TESTSET
from src.eval import metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run(retrieval_only: bool = False, persona: str = None):
    pipeline = RAGPipeline()
    pipeline.load_index()

    cases = TESTSET if not persona else [c for c in TESTSET if c["persona"] == persona]
    logger.info(f"共 {len(cases)} 条测试用例, 模式={'仅检索' if retrieval_only else '完整'}")

    per_case = []
    t_start = time.time()

    for i, case in enumerate(cases, 1):
        logger.info(f"[{i}/{len(cases)}] {case['id']} [{case['persona']}] {case['query']}")

        # 检索(只调用 retrieve, 不调用 LLM)
        if retrieval_only:
            results = pipeline.retriever.retrieve(
                query=case["query"], filters=case["constraints"] or None,
            )
            answer = ""
            sources = [{"title": r["metadata"].get("title", "")} for r in results]
        else:
            resp = pipeline.query(case["query"], filters=case["constraints"] or None)
            answer = resp.get("answer", "")
            sources = resp.get("sources", [])
            # 从 retriever 再跑一次 (或从 resp 解析) 以获取 metadata
            results = pipeline.retriever.retrieve(
                query=case["query"], filters=case["constraints"] or None,
            )

        hints = case["relevance_hints"]
        record = {
            "id": case["id"],
            "persona": case["persona"],
            "query": case["query"],
            "hit_rate": metrics.hit_rate(results, hints),
            "mrr": metrics.mrr(results, hints),
            "precision_at_k": metrics.precision_at_k(results, hints),
            "constraint_satisfaction": metrics.constraint_satisfaction_rate(
                results, case["constraints"]
            ),
        }
        if not retrieval_only:
            record["faithfulness"] = metrics.faithfulness_heuristic(answer, sources)
            record["answer_relevancy"] = metrics.answer_relevancy_heuristic(answer, case["query"])
        per_case.append(record)

    elapsed = time.time() - t_start
    summary = metrics.summarize(per_case)

    # 按画像分组汇总
    by_persona = {}
    for p in set(c["persona"] for c in cases):
        sub = [r for r in per_case if r["persona"] == p]
        by_persona[p] = metrics.summarize(sub)

    report = {
        "mode": "retrieval_only" if retrieval_only else "full",
        "elapsed_seconds": round(elapsed, 2),
        "overall": summary,
        "by_persona": by_persona,
        "per_case": per_case,
    }

    out = Path("paper/eval_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print("\n" + "=" * 60)
    print(f"评估完成, 耗时 {elapsed:.1f}s, 用例数 {len(cases)}")
    print("=" * 60)
    print("\n【整体指标】")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k:25s}: {v:.4f}")
        else:
            print(f"  {k:25s}: {v}")
    print("\n【按画像分组】")
    for p, s in by_persona.items():
        print(f"\n  [{p}]")
        for k, v in s.items():
            if isinstance(v, float):
                print(f"    {k:23s}: {v:.4f}")
    print(f"\n详细报告: {out}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true", help="只跑检索端评估")
    parser.add_argument("--persona", type=str, default=None, help="只跑指定画像")
    args = parser.parse_args()
    run(retrieval_only=args.retrieval_only, persona=args.persona)
