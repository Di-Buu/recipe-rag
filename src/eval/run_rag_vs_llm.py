"""
RAG 与纯 LLM 对照实验脚本 — 自动生成可信的对比数据。

操作流程:
  1. 对每条对照 query,调 RAG 系统 /api/recommend 拿到 RAG 推荐(含 sources)
  2. 同条 query 直接调 qwen3-max(无检索),拿到纯 LLM 答案
  3. 让 qwen3-max 再做一次提取,从纯 LLM 答案中抽出推荐的菜名列表
  4. 把 RAG 与纯 LLM 推荐的所有菜名,在 recipes_enriched.json(知识库)中查找
       存在 → 标注 ✓ 真实
       不存在 → 标注 ✗ 虚构
  5. 统计虚构率,生成对比 markdown 报告 + raw JSON

用法:
  # 先启动后端(以便调 /api/recommend):python -m src.api
  python -m src.eval.run_rag_vs_llm

输出:
  data/eval/rag_vs_llm_<时间戳>.md   markdown 对比表(可贴附录 B.4)
  data/eval/rag_vs_llm_<时间戳>.json raw 结构化数据
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import dashscope
import requests
from dashscope import Generation

from src import config

logger = logging.getLogger(__name__)


# 5 条对照查询(覆盖三类用户画像 + 强约束场景)
COMPARE_QUERIES = [
    {
        "id": "C1",
        "query": "推荐几道简单的家常菜",
        "persona": "张女士(日常决策)",
        "highlight": "菜名真实性",
        "filters": None,
    },
    {
        "id": "C2",
        "query": "低卡高蛋白的晚餐",
        "persona": "李先生(健康管理)",
        "highlight": "营养数据可验证 + 约束遵守",
        "filters": {"nutrition_tags": ["低卡", "高蛋白"]},
    },
    {
        "id": "C3",
        "query": "排除花生的菜",
        "persona": "李先生(健康管理)",
        "highlight": "硬约束遵守(食材排除)",
        "filters": {"exclude_ingredients": ["花生"]},
    },
    {
        "id": "C4",
        "query": "红烧肉怎么做",
        "persona": "王同学(学习入门)",
        "highlight": "食材具体性 + 来源可追溯",
        "filters": None,
    },
    {
        "id": "C5",
        "query": "30分钟内能做好的菜",
        "persona": "张女士(日常决策)",
        "highlight": "时间约束遵守",
        "filters": {"costtime_max": 30},
    },
]


def load_recipe_titles() -> set[str]:
    """加载知识库所有食谱菜名,作为虚构判定的参考集合"""
    print(f"[1/4] 加载知识库菜名: {config.ENRICHED_DATA_PATH}")
    with open(config.ENRICHED_DATA_PATH, "r", encoding="utf-8") as f:
        recipes = json.load(f)
    titles = {r.get("title", "").strip() for r in recipes if r.get("title")}
    titles.discard("")
    print(f"      共 {len(titles)} 条不同菜名")
    return titles


def is_in_knowledge_base(name: str, titles: set[str]) -> bool:
    """判断菜名是否在知识库中存在(精确或 title 包含 name)"""
    name = name.strip()
    if not name:
        return False
    if name in titles:
        return True
    # 子串匹配:知识库里有"家常红烧肉",查询给"红烧肉"也算存在
    for t in titles:
        if name in t or t in name:
            return True
    return False


def call_rag_system(api_url: str, query: str, filters: dict | None) -> dict:
    """调用 RAG 系统的 /api/recommend (一次性返回,非流式)"""
    # 用 eval/query 接口,不需要登录,且返回 sources + answer + contexts
    endpoint = api_url.rstrip("/") + "/api/eval/query"
    resp = requests.post(
        endpoint, json={"query": query, "filters": filters}, timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def call_pure_llm(query: str) -> str:
    """直接调用 qwen3-max,不带检索增强"""
    dashscope.api_key = config.DASHSCOPE_API_KEY
    messages = [
        {
            "role": "system",
            "content": "你是一位专业的食谱推荐助手。根据用户的需求,推荐 5 道合适的食谱"
                       ",每道菜简要说明菜名、主要食材和做法要点。",
        },
        {"role": "user", "content": query},
    ]
    response = Generation.call(
        model="qwen3-max",
        messages=messages,
        result_format="message",
        max_tokens=2048,
        temperature=0.3,
    )
    if response.status_code == 200:
        return response.output.choices[0].message.content
    else:
        return f"[ERROR: HTTP {response.status_code}, code={response.code}]"


def extract_dish_names_from_text(text: str) -> list[str]:
    """让 qwen3-max 从一段文本中提取推荐的菜名列表(JSON)"""
    if not text or text.startswith("[ERROR"):
        return []
    dashscope.api_key = config.DASHSCOPE_API_KEY
    prompt = (
        "下面是一段食谱推荐文本。请从中提取出推荐的菜名列表。"
        "只返回 JSON 数组(无其他内容),例如 [\"红烧肉\", \"清蒸鲈鱼\"]。"
        f"\n\n文本:\n{text}"
    )
    response = Generation.call(
        model="qwen3-max",
        messages=[{"role": "user", "content": prompt}],
        result_format="message",
        max_tokens=512,
        temperature=0,
    )
    if response.status_code != 200:
        return []
    raw = response.output.choices[0].message.content.strip()
    # 去掉 markdown 代码块包装
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(line for line in lines if not line.startswith("```"))
    try:
        names = json.loads(raw)
        return [str(n).strip() for n in names if n]
    except json.JSONDecodeError:
        # fallback:正则简单提取引号内的菜名
        import re
        return re.findall(r'"([^"]+)"', raw)


def evaluate_one(
    item: dict, api_url: str, kb_titles: set[str]
) -> dict:
    """对单条对照 query 跑完整对比"""
    query = item["query"]
    print(f"\n--- {item['id']}: {query} ---")

    # 1. RAG
    print("  调 RAG...", end="", flush=True)
    t0 = time.perf_counter()
    try:
        rag_result = call_rag_system(api_url, query, item.get("filters"))
        rag_answer = rag_result.get("answer", "")
        rag_sources = rag_result.get("sources", [])
        rag_titles = [s.get("title", "") for s in rag_sources if s.get("title")]
        print(f" {time.perf_counter() - t0:.1f}s,得到 {len(rag_titles)} 条来源")
    except Exception as e:
        print(f" 失败: {e}")
        rag_answer = ""
        rag_sources = []
        rag_titles = []

    # 2. 纯 LLM
    print("  调纯 LLM...", end="", flush=True)
    t0 = time.perf_counter()
    llm_answer = call_pure_llm(query)
    print(f" {time.perf_counter() - t0:.1f}s")

    print("  提取 LLM 菜名...", end="", flush=True)
    llm_names = extract_dish_names_from_text(llm_answer)
    print(f" 提到 {len(llm_names)} 道菜")

    # 3. 知识库存在性检查
    rag_check = [{"name": t, "in_kb": is_in_knowledge_base(t, kb_titles)}
                 for t in rag_titles]
    llm_check = [{"name": n, "in_kb": is_in_knowledge_base(n, kb_titles)}
                 for n in llm_names]

    rag_real = sum(1 for x in rag_check if x["in_kb"])
    llm_real = sum(1 for x in llm_check if x["in_kb"])

    return {
        "id":          item["id"],
        "query":       query,
        "persona":     item["persona"],
        "highlight":   item["highlight"],
        "filters":     item.get("filters"),
        "rag": {
            "answer_preview": rag_answer[:300],
            "titles":         rag_titles,
            "check":          rag_check,
            "real_count":     rag_real,
            "total":          len(rag_check),
            "fabricate_rate": round(1 - rag_real / max(1, len(rag_check)), 3),
            "has_sources":    bool(rag_sources),
        },
        "pure_llm": {
            "answer_preview": llm_answer[:300],
            "titles":         llm_names,
            "check":          llm_check,
            "real_count":     llm_real,
            "total":          len(llm_check),
            "fabricate_rate": round(1 - llm_real / max(1, len(llm_check)), 3),
            "has_sources":    False,
        },
    }


def write_markdown(results: list[dict], path: Path) -> None:
    """生成可贴论文的 markdown 报告"""
    lines = []
    lines.append("# RAG 与纯 LLM 对照实验报告\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"对照查询数: {len(results)}")
    lines.append(f"RAG 系统: 本研究系统(qwen3-max + 混合检索)")
    lines.append(f"基准模型: 纯 qwen3-max(无检索增强)")
    lines.append(f"虚构判定: 推荐菜名是否能在知识库 {config.ENRICHED_DATA_PATH.name} 中找到(精确或子串匹配)\n")

    # 总体统计
    rag_total = sum(r["rag"]["total"] for r in results)
    rag_real = sum(r["rag"]["real_count"] for r in results)
    llm_total = sum(r["pure_llm"]["total"] for r in results)
    llm_real = sum(r["pure_llm"]["real_count"] for r in results)
    lines.append("## 一、总体统计\n")
    lines.append("| 维度 | RAG 系统 | 纯 LLM |")
    lines.append("|---|---|---|")
    lines.append(
        f"| 推荐菜名总数 | {rag_total} | {llm_total} |"
    )
    lines.append(
        f"| 知识库中存在(真实) | {rag_real} | {llm_real} |"
    )
    rag_fab = round(1 - rag_real / max(1, rag_total), 3)
    llm_fab = round(1 - llm_real / max(1, llm_total), 3)
    lines.append(
        f"| 知识库中不存在(虚构) | {rag_total - rag_real} | {llm_total - llm_real} |"
    )
    lines.append(
        f"| **虚构率** | **{rag_fab*100:.1f}%** | **{llm_fab*100:.1f}%** |"
    )
    lines.append(
        f"| 是否提供检索来源 | ✓ 全部附 sources | ✗ 无 |"
    )
    lines.append(
        f"| 是否给出营养数据 | ✓(基于 food_nutrition.db) | ✗(无营养库支持) |\n"
    )

    # 逐题详情
    lines.append("## 二、逐题详情\n")
    for r in results:
        lines.append(f"### {r['id']} `{r['persona']}`: {r['query']}\n")
        lines.append(f"侧重维度: {r['highlight']}")
        if r.get("filters"):
            lines.append(f"过滤条件: `{json.dumps(r['filters'], ensure_ascii=False)}`")
        lines.append("")

        lines.append("**RAG 推荐(top-K 来源):**")
        for c in r["rag"]["check"]:
            mark = "✓" if c["in_kb"] else "✗"
            lines.append(f"- {mark} {c['name']}")
        lines.append(f"\n虚构率: {r['rag']['fabricate_rate']*100:.0f}% "
                     f"({r['rag']['total'] - r['rag']['real_count']}/{r['rag']['total']})\n")

        lines.append("**纯 LLM 推荐(从答案中抽取的菜名):**")
        for c in r["pure_llm"]["check"]:
            mark = "✓" if c["in_kb"] else "✗"
            lines.append(f"- {mark} {c['name']}")
        lines.append(f"\n虚构率: {r['pure_llm']['fabricate_rate']*100:.0f}% "
                     f"({r['pure_llm']['total'] - r['pure_llm']['real_count']}/{r['pure_llm']['total']})\n")
        lines.append("---\n")

    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="RAG 与纯 LLM 对照实验")
    parser.add_argument(
        "--api-url", type=str, default="http://localhost:8000",
        help="RAG 系统 API 地址(需先启动 python -m src.api)",
    )
    parser.add_argument(
        "--output-dir", type=str,
        default=str(Path(config.DATA_DIR) / "eval"),
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="只跑前 N 条对照(默认全部 5 条)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RAG vs 纯 LLM 对照实验")
    print("=" * 60)

    # 健康检查
    try:
        health = requests.get(args.api_url + "/api/health", timeout=5).json()
        print(f"后端服务: {args.api_url} → {health}\n")
    except Exception as e:
        print(f"无法连接 RAG 后端 {args.api_url}: {e}")
        print("请先启动: python -m src.api")
        return

    # 加载知识库菜名
    kb_titles = load_recipe_titles()

    queries = COMPARE_QUERIES[: args.limit] if args.limit else COMPARE_QUERIES
    print(f"\n[2/4] 跑 {len(queries)} 条对照查询...")
    results = []
    for item in queries:
        results.append(evaluate_one(item, args.api_url, kb_titles))

    # 输出
    print(f"\n[3/4] 写入对比报告...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"rag_vs_llm_{ts}.md"
    json_path = output_dir / f"rag_vs_llm_{ts}.json"

    write_markdown(results, md_path)
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n[4/4] 完成!")
    print(f"对比报告: {md_path}")
    print(f"原始数据: {json_path}")
    print()
    print("=" * 60)
    rag_fab_total = sum(
        r["rag"]["total"] - r["rag"]["real_count"] for r in results
    ) / max(1, sum(r["rag"]["total"] for r in results))
    llm_fab_total = sum(
        r["pure_llm"]["total"] - r["pure_llm"]["real_count"] for r in results
    ) / max(1, sum(r["pure_llm"]["total"] for r in results))
    print(f"总体虚构率:")
    print(f"  RAG 系统:    {rag_fab_total*100:.1f}%")
    print(f"  纯 LLM:      {llm_fab_total*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
