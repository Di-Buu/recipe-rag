"""
性能测试脚本 — 测各阶段真实耗时,输出可直接贴论文表 5-3 的结果。

测试环节:
1. Embedding 向量化(单条 query)
2. BM25 关键词检索
3. Qdrant 向量检索
4. RRF 融合 + 父文档聚合 + 约束过滤
5. 端到端检索(双路并行 + 聚合)
6. LLM 首 token 时间 + 完整生成时间
7. 端到端响应(检索 + 生成)

每环节跑 N 次取平均 + 标准差。

用法:
  # 先确保索引已建好:python -m src.pipeline.run_build_index
  # 然后跑性能测试(自带 Pipeline 加载,无需启动 FastAPI)
  python -m src.eval.run_perf_test
  python -m src.eval.run_perf_test --runs 10  # 每环节 10 次(默认 5 次)

输出:
  data/eval/perf_report_<时间戳>.md   markdown 表格,直接贴论文
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from datetime import datetime
from pathlib import Path

from llama_index.core import Settings
from llama_index.core.llms import ChatMessage, MessageRole

from src import config
from src.pipeline.indexer import RecipeIndexer
from src.pipeline.retriever import RecipeRetriever
from src.pipeline.rag_pipeline import RAGPipeline
from src.pipeline.prompt_templates import (
    build_system_prompt,
    build_qa_prompt,
    format_context,
    format_constraints,
)

logger = logging.getLogger(__name__)


# 用于性能测试的样本查询(覆盖三类画像)
PERF_QUERIES = [
    "推荐几道简单的家常菜",
    "低卡高蛋白的晚餐",
    "红烧肉怎么做",
    "30分钟内能做好的菜",
    "适合孩子吃的家常菜",
]


def fmt(values: list[float]) -> str:
    """格式化耗时统计(平均 ± 标准差,单位秒)"""
    if not values:
        return "—"
    avg = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"{avg:.3f} ± {sd:.3f}"


def time_section(label: str, runs: int, fn) -> dict:
    """通用计时器:跑 N 次,记录每次耗时,返回统计"""
    times = []
    print(f"  {label}: ", end="", flush=True)
    for i in range(runs):
        t0 = time.perf_counter()
        fn(i)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        print(".", end="", flush=True)
    avg = statistics.mean(times)
    sd = statistics.stdev(times) if len(times) > 1 else 0.0
    print(f"  → {avg:.3f}s ± {sd:.3f}s")
    return {
        "label": label,
        "runs": runs,
        "avg_s": round(avg, 4),
        "stdev_s": round(sd, 4),
        "min_s": round(min(times), 4),
        "max_s": round(max(times), 4),
        "all": [round(t, 4) for t in times],
    }


def main():
    parser = argparse.ArgumentParser(description="RAG 系统性能测试")
    parser.add_argument("--runs", type=int, default=5, help="每环节测试次数(默认 5)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(config.DATA_DIR) / "eval"),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,  # 减少日志噪声
        format="%(asctime)s %(levelname)s %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"RAG 系统性能测试 (每环节 {args.runs} 次)")
    print("=" * 60)
    print()

    # ------- 加载 Pipeline -------
    print("[1/2] 加载 Pipeline (Embedding + Qdrant + BM25)...")
    t0 = time.perf_counter()
    pipeline = RAGPipeline()
    pipeline.load_index()
    load_elapsed = time.perf_counter() - t0
    print(f"      Pipeline 加载完成,耗时 {load_elapsed:.1f}s")
    print()

    indexer = pipeline._indexer
    retriever = pipeline._retriever
    embed_model = Settings.embed_model

    # ------- 测试各环节 -------
    print(f"[2/2] 各阶段计时 (使用 {len(PERF_QUERIES)} 个样本 query 轮换):")
    results = {}

    # 1. Embedding 向量化
    def stage_embed(i):
        q = PERF_QUERIES[i % len(PERF_QUERIES)]
        embed_model.get_query_embedding(q)

    results["embed"] = time_section("Embedding 向量化         ", args.runs, stage_embed)

    # 2. BM25 检索
    def stage_bm25(i):
        q = PERF_QUERIES[i % len(PERF_QUERIES)]
        retriever._bm25_retrieve(q, top_k=config.RETRIEVAL_TOP_K)

    results["bm25"] = time_section("BM25 关键词检索          ", args.runs, stage_bm25)

    # 3. Qdrant 向量检索
    def stage_qdrant(i):
        q = PERF_QUERIES[i % len(PERF_QUERIES)]
        retriever._dense_retrieve(q, top_k=config.RETRIEVAL_TOP_K)

    results["qdrant"] = time_section("Qdrant 向量检索          ", args.runs, stage_qdrant)

    # 4. 端到端检索(双路 + RRF + 过滤 + 聚合)
    def stage_retrieve(i):
        q = PERF_QUERIES[i % len(PERF_QUERIES)]
        retriever.retrieve(q, top_k=config.TOP_K)

    results["retrieve_full"] = time_section(
        "端到端检索 (双路+融合+聚合)", args.runs, stage_retrieve
    )

    # 5. LLM 首 token 时间 + 完整生成
    print()
    print("LLM 调用测试 (使用样本 query 'low-cal high-protein dinner'):")
    test_query = PERF_QUERIES[1]
    parent_docs = retriever.retrieve(test_query, top_k=config.TOP_K)
    context = format_context(parent_docs, top_k=config.TOP_K)
    constraints = format_constraints(None)
    system_prompt = build_system_prompt()
    user_prompt = build_qa_prompt(context, test_query, constraints)
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
        ChatMessage(role=MessageRole.USER, content=user_prompt),
    ]

    first_token_times = []
    full_gen_times = []
    for i in range(args.runs):
        print(f"  LLM 调用 {i+1}/{args.runs}: ", end="", flush=True)
        t_start = time.perf_counter()
        first_t = None
        token_count = 0
        for chunk in Settings.llm.stream_chat(messages):
            if first_t is None and chunk.delta:
                first_t = time.perf_counter() - t_start
            if chunk.delta:
                token_count += 1
        full_t = time.perf_counter() - t_start
        first_token_times.append(first_t or 0.0)
        full_gen_times.append(full_t)
        print(
            f"首 token {first_t:.2f}s, "
            f"全生成 {full_t:.2f}s, {token_count} chunks"
        )

    results["llm_first_token"] = {
        "label": "LLM 首 token 时间        ",
        "runs": args.runs,
        "avg_s": round(statistics.mean(first_token_times), 4),
        "stdev_s": round(statistics.stdev(first_token_times), 4)
        if args.runs > 1
        else 0.0,
        "all": [round(t, 4) for t in first_token_times],
    }
    results["llm_full"] = {
        "label": "LLM 完整生成              ",
        "runs": args.runs,
        "avg_s": round(statistics.mean(full_gen_times), 4),
        "stdev_s": round(statistics.stdev(full_gen_times), 4)
        if args.runs > 1
        else 0.0,
        "all": [round(t, 4) for t in full_gen_times],
    }

    # 6. 端到端总耗时
    end_to_end = [
        results["retrieve_full"]["all"][i] + full_gen_times[i]
        for i in range(args.runs)
    ]
    results["end_to_end"] = {
        "label": "端到端响应 (检索+生成)   ",
        "runs": args.runs,
        "avg_s": round(statistics.mean(end_to_end), 4),
        "stdev_s": round(statistics.stdev(end_to_end), 4) if args.runs > 1 else 0.0,
        "all": [round(t, 4) for t in end_to_end],
    }

    # ------- 输出 markdown 报告 -------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"perf_report_{ts}.md"
    json_path = output_dir / f"perf_raw_{ts}.json"

    lines = []
    lines.append(f"# 系统性能测试报告\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"每环节测试次数: {args.runs}")
    lines.append(f"测试样本: {len(PERF_QUERIES)} 条用户画像查询轮换")
    lines.append(f"Pipeline 加载耗时: {load_elapsed:.2f}s (一次性,不计入下表)")
    lines.append("")
    lines.append("## 各阶段平均耗时\n")
    lines.append("| 测试环节 | 平均耗时 ± 标准差 (s) | 最小 (s) | 最大 (s) |")
    lines.append("|---|---|---|---|")

    order = ["embed", "bm25", "qdrant", "retrieve_full",
             "llm_first_token", "llm_full", "end_to_end"]
    label_map = {
        "embed":            "Embedding 向量化(单条 query)",
        "bm25":             "BM25 关键词检索",
        "qdrant":           "Qdrant 向量检索",
        "retrieve_full":    "端到端检索(双路+RRF+聚合)",
        "llm_first_token":  "LLM 首 token 时间",
        "llm_full":         "LLM 完整生成",
        "end_to_end":       "端到端响应(检索+生成)",
    }
    for k in order:
        r = results[k]
        avg = r["avg_s"]
        sd = r["stdev_s"]
        mn = r.get("min_s", min(r["all"]))
        mx = r.get("max_s", max(r["all"]))
        lines.append(
            f"| {label_map[k]} | {avg:.3f} ± {sd:.3f} | "
            f"{mn:.3f} | {mx:.3f} |"
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "load_elapsed_s": round(load_elapsed, 2),
                "runs": args.runs,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 60)
    print(f"性能报告: {md_path}")
    print(f"原始数据: {json_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
