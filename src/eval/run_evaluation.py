"""
基于 RAGAS 的 RAG 评估模块

评估体系(参考 Es et al., 2024 — RAGAS: Automated Evaluation of RAG, EACL 2024):
  - LLMContextPrecisionWithoutReference  检索侧:相关 context 是否排在前面(reference-free)
  - Faithfulness                         生成侧:答案是否忠实于检索上下文(幻觉检测)

两个都是 reference-free 指标,不依赖人工标注的"标准答案",更适合开放式多约束
query 场景(Es et al. 2024 论文指出的传统 IR 评估的局限)。

Judge 模型:
  - DeepSeek-V3.2 (跨厂商 judge,规避 Qwen 自评偏差,Zheng et al. 2023)
  - 通过 DashScope 托管的 OpenAI 兼容 + DashScope 原生接口均可;本脚本复用
    llama-index-llms-dashscope,通过 ragas 的 LlamaIndexLLMWrapper 接入

架构:
  - FastAPI 服务常驻 -> HTTP 调 /api/eval/query 拉 response + retrieved_contexts
  - 本脚本构造 RAGAS SingleTurnSample -> 调 metric.single_turn_ascore

Python 3.14 兼容说明:
  ragas 内部通过 nest_asyncio.apply() 对 asyncio 做猴子补丁,破坏了 Python 3.14
  严格化的 asyncio.timeout task context 检查。脚本开头用假模块屏蔽 nest_asyncio.apply()
  (我们不依赖它的同步包装能力,整个评估走标准 async)。

用法:
  # 终端 1 启动常驻服务
  python -m src.api

  # 终端 2 跑评估
  python -m src.eval.run_evaluation                    # 完整评估
  python -m src.eval.run_evaluation --limit 5          # 冒烟
  python -m src.eval.run_evaluation --skip-generation  # 仅检索侧 Context Precision
"""

from __future__ import annotations

# === Python 3.14 + ragas 兼容:在 import ragas 前屏蔽 nest_asyncio.apply() ===
import sys
import types as _types

_fake_nest = _types.ModuleType("nest_asyncio")
_fake_nest.apply = lambda *a, **kw: None  # noqa: E731
sys.modules["nest_asyncio"] = _fake_nest
# ============================================================================

import argparse
import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from llama_index.llms.dashscope import DashScope
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import LlamaIndexLLMWrapper
from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

from src import config

logger = logging.getLogger(__name__)


# =========================================================================
# HTTP 调用
# =========================================================================


def call_eval_query(
    api_url: str,
    query: str,
    filters: dict | None = None,
    timeout: float = 300.0,
) -> dict:
    """调用 /api/eval/query,返回 {answer, contexts, sources}"""
    endpoint = api_url.rstrip("/") + "/api/eval/query"
    resp = requests.post(
        endpoint,
        json={"query": query, "filters": filters},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def call_eval_retrieve(
    api_url: str,
    query: str,
    filters: dict | None = None,
    top_k: int | None = None,
    timeout: float = 300.0,
) -> list[dict]:
    """调用 /api/eval/retrieve,返回 results 列表(含 text 字段)"""
    endpoint = api_url.rstrip("/") + "/api/eval/retrieve"
    resp = requests.post(
        endpoint,
        json={"query": query, "filters": filters, "top_k": top_k},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def check_service_ready(api_url: str, timeout: float = 5.0) -> None:
    """启动前预检查常驻服务是否可用"""
    health = api_url.rstrip("/") + "/api/health"
    try:
        resp = requests.get(health, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(
            f"无法连接到常驻服务 {api_url}: {e}\n"
            "请先在另一个终端启动: python -m src.api"
        ) from e
    if not data.get("pipeline_ready"):
        raise RuntimeError(
            f"服务已启动但 Pipeline 未就绪: {data}\n"
            "等待启动完成后再运行评估"
        )
    logger.info(f"常驻服务健康检查通过: {data}")


# =========================================================================
# RAGAS judge 配置
# =========================================================================


def build_judge_llm():
    """创建 RAGAS judge LLM(DashScope 托管的 DeepSeek-V3.2,跨厂商规避自评偏差)"""
    return LlamaIndexLLMWrapper(DashScope(
        model_name=config.JUDGE_MODEL,
        api_key=config.DASHSCOPE_API_KEY,
        temperature=config.JUDGE_TEMPERATURE,
        max_tokens=config.JUDGE_MAX_TOKENS,
        timeout=120,
    ))


# =========================================================================
# 评估主流程
# =========================================================================


def load_testset(path: Path) -> list[dict]:
    """兼容 dict(含 items 字段)和 list 两种测试集格式"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("items") or []
    return data


async def evaluate_all(
    items: list[dict],
    api_url: str,
    context_precision,
    faithfulness,
    skip_generation: bool,
) -> tuple[dict, dict, list[dict], list[dict]]:
    """
    对每道题一次性:HTTP 拉 response+contexts,同时跑 CP + Faithfulness。

    LLMContextPrecisionWithoutReference 的"WithoutReference"指不需要 ground-truth
    reference_contexts,但仍需要 response 作为"参考答案"(判断 context 是否对
    response 的生成有用)。因此必须走完整 RAG,不能仅 retrieve。
    """
    cp_scores: list[float] = []
    cp_per_persona: dict[str, list[float]] = defaultdict(list)
    cp_details: list[dict] = []

    faith_scores: list[float] = []
    faith_per_persona: dict[str, list[float]] = defaultdict(list)
    faith_details: list[dict] = []

    for idx, item in enumerate(items, 1):
        query = item["query"]
        filters = item.get("filters") or None
        persona = item.get("persona", "unknown")

        # 1. 完整 RAG 调用:一次 HTTP 拿 response + contexts
        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                call_eval_query, api_url, query, filters,
            )
        except Exception as e:
            logger.error(f"[{item['id']}] /eval/query 调用失败: {e}")
            continue
        rag_elapsed = time.perf_counter() - t0

        answer = result.get("answer", "") or ""
        contexts = result.get("contexts", []) or []
        sources = result.get("sources", []) or []
        if not contexts:
            logger.warning(f"[{item['id']}] 无检索结果,跳过")
            continue

        sample = SingleTurnSample(
            user_input=query,
            response=answer,
            retrieved_contexts=contexts,
        )
        top_titles = [s.get("title", "") for s in sources[:5]]

        # 2. Context Precision(需要 response 作为参考)
        t_cp = time.perf_counter()
        cp_score: float | None = None
        try:
            cp_score = await context_precision.single_turn_ascore(sample)
        except Exception as e:
            logger.error(f"[{item['id']}] ContextPrecision judge 失败: {e}")
        cp_elapsed = time.perf_counter() - t_cp

        if cp_score is not None:
            cp_scores.append(cp_score)
            cp_per_persona[persona].append(cp_score)
            cp_details.append({
                "id": item["id"],
                "persona": persona,
                "query": query,
                "context_precision": round(cp_score, 4),
                "retrieved_top5_titles": top_titles,
                "judge_elapsed_s": round(cp_elapsed, 2),
            })

        # 3. Faithfulness(需要 answer + contexts)
        faith_score: float | None = None
        faith_elapsed = 0.0
        if not skip_generation and answer:
            t_f = time.perf_counter()
            try:
                faith_score = await faithfulness.single_turn_ascore(sample)
            except Exception as e:
                logger.error(f"[{item['id']}] Faithfulness judge 失败: {e}")
            faith_elapsed = time.perf_counter() - t_f

            if faith_score is not None:
                faith_scores.append(faith_score)
                faith_per_persona[persona].append(faith_score)
                faith_details.append({
                    "id": item["id"],
                    "persona": persona,
                    "query": query,
                    "faithfulness": round(faith_score, 4),
                    "answer_preview": answer[:200],
                    "judge_elapsed_s": round(faith_elapsed, 2),
                })

        logger.info(
            f"  [{idx}/{len(items)}] {item['id']} · {persona:20s} · "
            f"CP={'%.3f' % cp_score if cp_score is not None else 'N/A':>5s} · "
            f"Faith={'%.3f' % faith_score if faith_score is not None else '----':>5s} · "
            f"(RAG {rag_elapsed:.0f}s + CP {cp_elapsed:.0f}s + F {faith_elapsed:.0f}s)"
        )

    retrieval_summary = {
        "llm_context_precision": (
            round(sum(cp_scores) / len(cp_scores), 4) if cp_scores else 0
        ),
        "per_persona": {
            p: round(sum(s) / len(s), 4)
            for p, s in cp_per_persona.items() if s
        },
    }
    gen_summary = {
        "faithfulness": (
            round(sum(faith_scores) / len(faith_scores), 4) if faith_scores else 0
        ),
        "per_persona": {
            p: round(sum(s) / len(s), 4)
            for p, s in faith_per_persona.items() if s
        },
    } if faith_scores else {}
    return retrieval_summary, gen_summary, cp_details, faith_details


# =========================================================================
# 报告
# =========================================================================


def write_report(
    retrieval_summary: dict,
    retrieval_details: list[dict],
    gen_summary: dict,
    gen_details: list[dict],
    output_path: Path,
    total_elapsed: float,
) -> None:
    lines: list[str] = []
    lines.append(f"# RAG 系统评估报告(RAGAS)")
    lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"总耗时: {total_elapsed:.1f} 秒")
    lines.append(f"评估框架: RAGAS 0.2.15 (Es et al., EACL 2024)")
    lines.append(
        f"生成模型: {config.DASHSCOPE_MODEL} (DashScope, "
        f"temperature={config.LLM_TEMPERATURE})"
    )
    lines.append(
        f"Judge 模型: {config.JUDGE_MODEL} "
        f"(DashScope, temperature={config.JUDGE_TEMPERATURE}) — 跨厂商 judge"
    )

    # 检索侧
    lines.append(f"\n## 一、检索侧(LLMContextPrecisionWithoutReference)")
    lines.append(f"\n**定义**:判断检索到的 top-K 中相关 context 是否排在前列(reference-free)")
    lines.append(
        f"\n- **Context Precision**: "
        f"{retrieval_summary.get('llm_context_precision', 0):.3f}"
    )
    lines.append(f"\n### 按画像(Persona)分组")
    lines.append("\n| 画像 | Context Precision |")
    lines.append("|---|---|")
    for p, s in retrieval_summary.get("per_persona", {}).items():
        lines.append(f"| {p} | {s:.3f} |")

    # 生成侧
    if gen_summary:
        lines.append(f"\n## 二、生成侧(Faithfulness)")
        lines.append(
            f"\n**定义**:答案陈述是否能从检索上下文中推断得出(幻觉检测,reference-free)"
        )
        lines.append(
            f"\n- **Faithfulness**: {gen_summary.get('faithfulness', 0):.3f}"
        )
        lines.append(f"\n### 按画像分组")
        lines.append("\n| 画像 | Faithfulness |")
        lines.append("|---|---|")
        for p, s in gen_summary.get("per_persona", {}).items():
            lines.append(f"| {p} | {s:.3f} |")

    lines.append(f"\n## 三、逐题详情")
    lines.append(f"\n### 检索侧")
    for d in retrieval_details:
        lines.append(
            f"\n- **{d['id']}** `{d['persona']}` | `{d['query']}` | "
            f"CP={d['context_precision']:.3f} "
            f"(judge {d['judge_elapsed_s']}s)"
        )

    if gen_details:
        lines.append(f"\n### 生成侧")
        for d in gen_details:
            lines.append(
                f"\n- **{d['id']}** `{d['persona']}` | `{d['query']}` | "
                f"Faith={d['faithfulness']:.3f} "
                f"(judge {d['judge_elapsed_s']}s)"
            )
            lines.append(f"  - 答案片段: {d['answer_preview'][:120]}...")

    output_path.write_text("\n".join(lines), encoding="utf-8")


# =========================================================================
# main
# =========================================================================


async def async_main(args) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 健康检查
    check_service_ready(args.api_url)

    # 2. 加载测试集
    items = load_testset(Path(args.testset))
    if args.limit:
        items = items[: args.limit]
    logger.info(f"测试集 {len(items)} 题")

    # 3. 配置 judge LLM + 指标
    logger.info(
        f"配置 judge: {config.JUDGE_MODEL} "
        f"(temperature={config.JUDGE_TEMPERATURE}) — 跨厂商 judge"
    )
    judge = build_judge_llm()
    context_precision = LLMContextPrecisionWithoutReference(llm=judge)
    faithfulness = Faithfulness(llm=judge)

    t_start = time.perf_counter()

    # 4. 合并评估:一次 HTTP 同时跑 CP 和 Faithfulness
    logger.info(
        "=== RAGAS 评估(合并 pass):ContextPrecision + "
        f"{'Faithfulness' if not args.skip_generation else '(生成侧跳过)'}"
    )
    retrieval_summary, gen_summary, retrieval_details, gen_details = await evaluate_all(
        items, args.api_url, context_precision, faithfulness, args.skip_generation,
    )

    total_elapsed = time.perf_counter() - t_start

    # 6. 报告
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"report_{ts}.md"
    raw_path = output_dir / f"raw_{ts}.json"

    write_report(
        retrieval_summary,
        retrieval_details,
        gen_summary,
        gen_details,
        report_path,
        total_elapsed,
    )
    raw_path.write_text(
        json.dumps(
            {
                "retrieval": {
                    "summary": retrieval_summary,
                    "details": retrieval_details,
                },
                "generation": {"summary": gen_summary, "details": gen_details},
                "total_elapsed_s": round(total_elapsed, 2),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"报告已保存: {report_path}")
    logger.info(f"原始数据: {raw_path}")

    print("\n" + "=" * 60)
    print(f"评估完成 · 耗时 {total_elapsed:.1f}s")
    print("=" * 60)
    print(
        f"[检索侧] Context Precision = "
        f"{retrieval_summary.get('llm_context_precision', 0):.3f}"
    )
    if gen_summary:
        print(
            f"[生成侧] Faithfulness     = "
            f"{gen_summary.get('faithfulness', 0):.3f}"
        )
    print(f"报告: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="基于 RAGAS 的 RAG 评估")
    parser.add_argument("--limit", type=int, default=None, help="仅评估前 N 题")
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="仅跑检索侧 Context Precision",
    )
    parser.add_argument(
        "--testset",
        type=str,
        default=str(Path(__file__).parent / "testset.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(config.DATA_DIR) / "eval"),
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
