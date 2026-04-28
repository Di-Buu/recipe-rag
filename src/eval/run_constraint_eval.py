"""
约束满足率评估(独立评估维度,补充 RAGAS)

动机:
  RAGAS 的 Faithfulness/ContextPrecision 指标评估"检索/生成的质量",但无法回答
  "硬约束是否被遵守"这类系统特性问题。例如 Q20 "排除花生的菜",系统必须保证
  top-K 结果中 **全部不含花生**,这是一个二元约束,而非语义相关性问题。

  本脚本对测试集中带 filters 的题目单独统计:
    - exclude_ingredients:   top-K 中不含排除食材的比例
    - include_ingredients:   top-K 中包含指定食材的比例
    - nutrition_tags:        top-K 中带有指定营养标签的比例
    - costtime_max:          top-K 中耗时 ≤ 阈值的比例
    - difficulty_max:        top-K 中难度 ≤ 阈值的比例

  "硬约束满足率"与 RAGAS 的 LLM judge 指标互补,覆盖系统的"确定性行为"维度。

用法:
  # 先启动常驻服务: python -m src.api
  python -m src.eval.run_constraint_eval
  python -m src.eval.run_constraint_eval --limit 5
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

from src import config

logger = logging.getLogger(__name__)


# =========================================================================
# HTTP
# =========================================================================


def call_eval_retrieve(
    api_url: str, query: str, filters: dict | None, top_k: int, timeout: float = 120.0,
) -> list[dict]:
    endpoint = api_url.rstrip("/") + "/api/eval/retrieve"
    resp = requests.post(
        endpoint,
        json={"query": query, "filters": filters, "top_k": top_k},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


# =========================================================================
# 约束检查函数
# =========================================================================


def _get_all_ingredients(meta: dict) -> list[str]:
    """合并主料和辅料为统一列表"""
    main = meta.get("main_ingredients") or []
    sub = meta.get("sub_ingredients") or []
    if isinstance(sub, str):
        sub = []
    return list(main) + list(sub)


def check_exclude_ingredients(meta: dict, excludes: list[str]) -> bool:
    """检查食谱是否不含排除食材(True = 满足约束)"""
    ings = _get_all_ingredients(meta)
    return not any(ex in ing for ex in excludes for ing in ings)


def check_include_ingredients(meta: dict, includes: list[str]) -> bool:
    """检查食谱是否包含指定食材(全部)"""
    ings = _get_all_ingredients(meta)
    return all(any(inc in ing for ing in ings) for inc in includes)


def check_nutrition_tags(meta: dict, required_tags: list[str]) -> bool:
    """检查食谱是否带有任一指定营养标签"""
    recipe_tags = meta.get("nutrition_tags") or []
    return any(tag in recipe_tags for tag in required_tags)


def check_costtime_max(meta: dict, max_minutes: int) -> bool:
    """检查食谱耗时是否 ≤ 阈值"""
    t = meta.get("costtime_minutes")
    if t is None:
        return False  # 无信息视为不满足(保守)
    return t <= max_minutes


def check_difficulty_max(meta: dict, max_level: int) -> bool:
    """检查食谱难度是否 ≤ 阈值"""
    d = meta.get("difficulty")
    if d is None:
        return False
    return d <= max_level


# =========================================================================
# 主流程
# =========================================================================


def load_testset(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("items") or []
    return data


def evaluate_constraints(items: list[dict], api_url: str, top_k: int) -> dict:
    """对每道带 filters 的题目,统计 top-K 中满足各约束的比例"""
    # 按约束类型分组累计
    constraint_stats: dict[str, list[dict]] = defaultdict(list)
    per_item_details: list[dict] = []

    skipped_no_filters = 0

    for idx, item in enumerate(items, 1):
        filters = item.get("filters") or {}
        if not filters:
            skipped_no_filters += 1
            continue

        query = item["query"]
        item_id = item["id"]

        t0 = time.perf_counter()
        try:
            results = call_eval_retrieve(api_url, query, filters, top_k)
        except Exception as e:
            logger.error(f"[{item_id}] retrieve 失败: {e}")
            continue
        elapsed = time.perf_counter() - t0

        if not results:
            logger.warning(f"[{item_id}] 无检索结果,跳过")
            continue

        item_detail: dict = {
            "id": item_id,
            "query": query,
            "filters": filters,
            "retrieved_count": len(results),
            "elapsed_s": round(elapsed, 2),
            "constraints": {},
        }

        # 针对每个 filter 字段计算满足率
        for constraint_name, check_fn, value in _iter_constraints(filters):
            satisfied_count = sum(
                1 for r in results
                if check_fn(r.get("metadata") or {}, value)
            )
            rate = satisfied_count / len(results)
            item_detail["constraints"][constraint_name] = {
                "value": value,
                "satisfied": satisfied_count,
                "total": len(results),
                "rate": round(rate, 4),
            }
            constraint_stats[constraint_name].append(rate)

        per_item_details.append(item_detail)
        satisfied_summary = ", ".join(
            f"{k}={v['rate']:.2f}" for k, v in item_detail["constraints"].items()
        )
        logger.info(
            f"  [{idx}/{len(items)}] {item_id:4s} | {query[:30]:30s} | {satisfied_summary}"
        )

    # 汇总:每种约束的平均满足率
    summary: dict = {}
    for constraint_name, rates in constraint_stats.items():
        summary[constraint_name] = {
            "mean_satisfaction_rate": round(sum(rates) / len(rates), 4),
            "evaluated_items": len(rates),
        }

    return {
        "summary": summary,
        "details": per_item_details,
        "skipped_no_filters": skipped_no_filters,
    }


def _iter_constraints(filters: dict):
    """把 filters dict 展开为 (name, check_fn, value) 元组迭代"""
    if filters.get("exclude_ingredients"):
        yield ("exclude_ingredients", check_exclude_ingredients, filters["exclude_ingredients"])
    if filters.get("include_ingredients"):
        yield ("include_ingredients", check_include_ingredients, filters["include_ingredients"])
    if filters.get("nutrition_tags"):
        yield ("nutrition_tags", check_nutrition_tags, filters["nutrition_tags"])
    if filters.get("costtime_max") is not None:
        yield ("costtime_max", check_costtime_max, filters["costtime_max"])
    if filters.get("difficulty_max") is not None:
        yield ("difficulty_max", check_difficulty_max, filters["difficulty_max"])


def write_report(result: dict, output_path: Path, total_elapsed: float, total_items: int) -> None:
    lines: list[str] = []
    lines.append(f"# 约束满足率评估报告")
    lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"总耗时: {total_elapsed:.1f} 秒")
    lines.append(f"测试集总题数: {total_items}")
    lines.append(f"有 filters 的题数: {total_items - result['skipped_no_filters']}")

    lines.append(f"\n## 一、各约束类型汇总")
    lines.append(f"\n| 约束类型 | 平均满足率 | 涉及题数 |")
    lines.append("|---|---|---|")
    for name, stat in result["summary"].items():
        lines.append(
            f"| `{name}` | {stat['mean_satisfaction_rate']:.3f} | "
            f"{stat['evaluated_items']} |"
        )

    lines.append(f"\n## 二、逐题详情")
    for d in result["details"]:
        lines.append(f"\n### {d['id']} · `{d['query']}`")
        lines.append(f"- filters: `{d['filters']}`")
        lines.append(f"- 检索到 {d['retrieved_count']} 条,耗时 {d['elapsed_s']}s")
        for name, info in d["constraints"].items():
            lines.append(
                f"  - **{name}** = `{info['value']}` → "
                f"满足 {info['satisfied']}/{info['total']} 条 "
                f"(满足率 **{info['rate']:.3f}**)"
            )

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="约束满足率评估")
    parser.add_argument("--limit", type=int, default=None, help="仅评估前 N 题")
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
    parser.add_argument(
        "--top-k",
        type=int,
        default=config.TOP_K,
        help="每题评估的 top-K 检索结果数",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = load_testset(Path(args.testset))
    if args.limit:
        items = items[: args.limit]
    logger.info(f"测试集 {len(items)} 题")

    t_start = time.perf_counter()
    result = evaluate_constraints(items, args.api_url, args.top_k)
    total_elapsed = time.perf_counter() - t_start

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"constraint_report_{ts}.md"
    raw_path = output_dir / f"constraint_raw_{ts}.json"

    write_report(result, report_path, total_elapsed, len(items))
    raw_path.write_text(
        json.dumps(
            {**result, "total_elapsed_s": round(total_elapsed, 2)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logger.info(f"报告已保存: {report_path}")
    logger.info(f"原始数据: {raw_path}")

    print("\n" + "=" * 60)
    print(f"约束满足率评估完成 · 耗时 {total_elapsed:.1f}s")
    print("=" * 60)
    for name, stat in result["summary"].items():
        print(
            f"  {name:22s}: {stat['mean_satisfaction_rate']:.3f} "
            f"({stat['evaluated_items']} 题)"
        )


if __name__ == "__main__":
    main()
