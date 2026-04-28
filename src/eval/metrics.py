"""
RAG 评估指标（RAGAS 风格的轻量化实现）

本模块实现的指标借鉴了 RAGAS[Es 2024] 和经典 IR 评估方法[Manning 2008]:
- 检索端: Hit Rate, MRR, Precision@K
- 生成端: Faithfulness (忠实度,启发式), Answer Relevancy (启发式)

完整 LLM-as-Judge 版本见 RAGAS 官方库; 本实现避免额外 LLM 调用成本,
用关键词/来源匹配的启发式规则近似指标, 适合资源受限的本科毕设场景。
"""

from typing import Any


def is_relevant(meta: dict, hints: dict) -> bool:
    """
    根据 relevance_hints 判定单条结果是否相关。

    任一条件族满足即算相关(OR 逻辑):
    - title_contains: title 包含列表中任一关键词
    - main_ingredients_any: main_ingredients 与列表有任一交集
    - tags_any: tags 与列表有任一交集
    - nutrition_tags_any: nutrition_tags 与列表有任一交集
    """
    title = (meta.get("title") or "").lower()
    main_ings = [x.lower() for x in meta.get("main_ingredients", [])]
    tags = [x.lower() for x in meta.get("tags", [])]
    nut_tags = [x.lower() for x in meta.get("nutrition_tags", [])]

    if any(kw.lower() in title for kw in hints.get("title_contains", [])):
        return True
    if set(x.lower() for x in hints.get("main_ingredients_any", [])) & set(main_ings):
        return True
    if set(x.lower() for x in hints.get("tags_any", [])) & set(tags):
        return True
    if set(x.lower() for x in hints.get("nutrition_tags_any", [])) & set(nut_tags):
        return True
    return False


def hit_rate(results: list[dict], hints: dict) -> int:
    """Hit Rate: top-K 中至少一条相关即为 1,否则 0。"""
    return 1 if any(is_relevant(r["metadata"], hints) for r in results) else 0


def mrr(results: list[dict], hints: dict) -> float:
    """MRR (Mean Reciprocal Rank): 第一个相关结果的排名倒数。"""
    for rank, r in enumerate(results, start=1):
        if is_relevant(r["metadata"], hints):
            return 1.0 / rank
    return 0.0


def precision_at_k(results: list[dict], hints: dict) -> float:
    """Precision@K: top-K 中相关结果的比例。"""
    if not results:
        return 0.0
    n_relevant = sum(1 for r in results if is_relevant(r["metadata"], hints))
    return n_relevant / len(results)


def constraint_satisfaction_rate(results: list[dict], constraints: dict) -> float:
    """
    约束满足率: top-K 中满足用户约束的比例。
    对应 RAGAS 的 Context Precision 在带约束场景的延伸。
    """
    if not results or not constraints:
        return 1.0

    n_ok = 0
    for r in results:
        meta = r["metadata"]
        ok = True

        # 硬约束: nutrition_tags
        req_tags = constraints.get("nutrition_tags") or []
        if req_tags:
            actual = meta.get("nutrition_tags", [])
            if not any(t in actual for t in req_tags):
                ok = False

        # 硬约束: exclude_ingredients
        exc = constraints.get("exclude_ingredients") or []
        if exc and ok:
            all_ings = list(meta.get("main_ingredients", [])) + list(meta.get("sub_ingredients", []) or [])
            if any(e in all_ings for e in exc):
                ok = False

        # 硬约束: include_ingredients
        inc = constraints.get("include_ingredients") or []
        if inc and ok:
            main_ings = meta.get("main_ingredients", [])
            if not any(i in main_ings for i in inc):
                ok = False

        # 弹性约束: difficulty_max
        d_max = constraints.get("difficulty_max")
        if d_max is not None and ok:
            d = meta.get("difficulty")
            if d is not None and d > d_max:
                ok = False

        # 弹性约束: costtime_max
        c_max = constraints.get("costtime_max")
        if c_max is not None and ok:
            c = meta.get("costtime_minutes")
            if c is not None and c > c_max:
                ok = False

        if ok:
            n_ok += 1
    return n_ok / len(results)


def faithfulness_heuristic(answer: str, sources: list[dict]) -> float:
    """
    Faithfulness 启发式实现 (受 RAGAS 启发):
    答案中提到的食谱标题是否都能在 sources 中找到。
    计算方式: 答案中识别出的候选菜名关键词, 出现在任一 source title 中的比例。

    答案是否忠实于检索, 完整版应用 LLM-as-Judge;
    这里用关键词重合作为轻量代理。
    """
    if not sources:
        return 0.0
    titles = [(s.get("title") or "").strip() for s in sources]
    title_joined = " ".join(titles)
    # 粗略检测答案中的 Markdown 标题(### 菜名)
    import re
    mentioned = re.findall(r"#{1,4}\s*([^\n#]+)", answer or "")
    if not mentioned:
        return 1.0  # 无可验证菜名视为默认通过
    hit = sum(1 for m in mentioned if any(part in title_joined for part in m.strip().split()))
    return hit / len(mentioned)


def answer_relevancy_heuristic(answer: str, query: str) -> float:
    """
    Answer Relevancy 启发式实现 (受 RAGAS 启发):
    查询中的关键字符在答案里的命中率。中文场景用字符级近似。
    """
    if not query or not answer:
        return 0.0
    import jieba
    q_tokens = [t for t in jieba.lcut(query) if len(t) > 1]
    if not q_tokens:
        return 1.0
    hit = sum(1 for t in q_tokens if t in answer)
    return hit / len(q_tokens)


def summarize(per_case: list[dict]) -> dict:
    """聚合多条测试用例的平均指标。"""
    if not per_case:
        return {}
    keys = ["hit_rate", "mrr", "precision_at_k", "constraint_satisfaction",
            "faithfulness", "answer_relevancy"]
    summary = {}
    for k in keys:
        values = [c.get(k) for c in per_case if c.get(k) is not None]
        summary[k] = sum(values) / len(values) if values else 0.0
    summary["n_cases"] = len(per_case)
    return summary
