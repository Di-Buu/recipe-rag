"""
文档构建器模块（document_builder）

采用父子文本块策略，将结构化食谱数据转换为适用于 RAG 检索的文档结构。

设计原则：
- 只返回纯 Python 数据结构（字典/列表），不引入 LlamaIndex 依赖
- 每个食谱生成 1 个父文档 + 3 个子块（info / ingredient / step）
- 子块各自聚焦不同检索意图，提高召回率
"""

import re
from typing import Optional

# =========================================================================
# 常量与映射表
# =========================================================================

DIFFICULTY_MAP = {
    0: "简单",
    1: "一般",
    2: "较难",
    3: "困难",
}

CONFIDENCE_MAP = {
    "high": "可靠",
    "partial": "仅供参考",
    "low": "数据不足",
}


# =========================================================================
# 工具函数
# =========================================================================

def parse_costtime_minutes(costtime: str) -> Optional[int]:
    """
    将耗时文本转为分钟数（取区间中值）。

    规则：
    - "10-30分钟" → 20
    - "30-60分钟" → 45
    - "10分钟左右" → 10
    - "1小时以上" → 90
    - "1-2小时"   → 90
    - "数天"      → 1440
    - ""          → None
    """
    if not costtime or not costtime.strip():
        return None

    text = costtime.strip()

    if text == "数天":
        return 1440

    # "X-Y小时" 格式
    m = re.match(r"(\d+)-(\d+)小时", text)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        return (low + high) * 60 // 2

    # "X小时以上" 格式
    m = re.match(r"(\d+)小时以上", text)
    if m:
        return int(m.group(1)) * 60 + 30

    # "X-Y分钟" 格式
    m = re.match(r"(\d+)-(\d+)分钟", text)
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2

    # "X分钟左右" 或 "X分钟" 格式
    m = re.match(r"(\d+)分钟", text)
    if m:
        return int(m.group(1))

    return None


def _get_main_ingredients(recipe: dict) -> list[str]:
    """获取主食材列表（排除调味品），取前5个。"""
    nutrition_list = recipe.get("ingredient_nutrition") or []
    return [
        item["name"]
        for item in nutrition_list
        if item.get("match_type") != "seasoning"
    ][:5]


def _get_main_nutrition_items(recipe: dict) -> list[dict]:
    """获取主食材的营养条目（排除调味品）。"""
    nutrition_list = recipe.get("ingredient_nutrition") or []
    return [
        item for item in nutrition_list
        if item.get("match_type") != "seasoning"
    ]


# =========================================================================
# 共享元数据构建
# =========================================================================

def _build_base_metadata(recipe: dict) -> dict:
    """构建所有子块共享的基础元数据。"""
    difficulty = recipe.get("difficulty", 3)
    costtime = recipe.get("costtime", "")

    return {
        "recipe_id": str(recipe.get("did", "")),
        "title": recipe.get("title", ""),
        "category": recipe.get("zid", ""),
        "tags": recipe.get("tags") or [],
        "difficulty": difficulty,
        "difficulty_text": DIFFICULTY_MAP.get(difficulty, "未知"),
        "costtime": costtime,
        "costtime_minutes": parse_costtime_minutes(costtime),
        "ingredient_count": recipe.get("ingredient_count", 0),
        "main_ingredients": _get_main_ingredients(recipe),
        "viewnum": recipe.get("viewnum", 0),
        "favnum": recipe.get("favnum", 0),
        "nutrition_coverage": recipe.get("nutrition_coverage", 0.0),
        "nutrition_tags": recipe.get("nutrition_tags") or [],
        "nutrition_confidence": recipe.get("nutrition_confidence", "low"),
        "has_video": bool(recipe.get("videourl")),
        "thumb": recipe.get("thumb", ""),
    }


# =========================================================================
# 父文档构建
# =========================================================================

def _build_ingredient_lines(recipe: dict) -> list[str]:
    """构建食材列表行，将 ingredients_raw 与 quantities 配对。"""
    raw = recipe.get("ingredients_raw") or []
    quantities = recipe.get("quantities") or []

    lines = []
    for i, name in enumerate(raw):
        if quantities and i < len(quantities) and quantities[i]:
            lines.append(f"  - {name} {quantities[i]}")
        else:
            lines.append(f"  - {name}")
    return lines


def _build_nutrition_section(recipe: dict) -> list[str]:
    """构建营养概况段落，low 置信度时不输出。"""
    confidence = recipe.get("nutrition_confidence", "low")
    if confidence == "low":
        return []

    summary = recipe.get("nutrition_summary") or {}
    if not summary:
        return []

    tags = recipe.get("nutrition_tags") or []
    confidence_text = CONFIDENCE_MAP.get(confidence, "未知")

    lines = [
        "",
        "营养概况（每100g均值）：",
        f"  热量 {summary.get('energy', 0)}kcal | "
        f"蛋白质 {summary.get('protein', 0)}g | "
        f"脂肪 {summary.get('fat', 0)}g | "
        f"碳水 {summary.get('carbs', 0)}g",
    ]

    if tags:
        lines.append(f"  营养标签：{','.join(tags)}")
    else:
        lines.append("  营养标签：无")

    lines.append(f"  （置信度：{confidence_text}）")

    return lines


def _build_parent_text(recipe: dict) -> str:
    """构建父文档的完整文本。"""
    difficulty = recipe.get("difficulty", 3)
    difficulty_text = DIFFICULTY_MAP.get(difficulty, "未知")
    title = recipe.get("title", "")
    zid = recipe.get("zid", "")
    costtime = recipe.get("costtime", "")
    desc = recipe.get("desc", "")
    tip = recipe.get("tip", "")
    steps = recipe.get("steps") or []

    lines = [
        f"【{title}】",
        f"分类：{zid} | 难度：{difficulty_text} | 耗时：{costtime}",
    ]

    if desc:
        lines.append(f"描述：{desc}")

    # 食材列表
    ingredient_lines = _build_ingredient_lines(recipe)
    if ingredient_lines:
        lines.append("")
        lines.append("食材：")
        lines.extend(ingredient_lines)

    # 营养概况
    nutrition_lines = _build_nutrition_section(recipe)
    lines.extend(nutrition_lines)

    # 做法步骤
    if steps:
        lines.append("")
        lines.append("做法步骤：")
        for step in steps:
            lines.append(f"  {step}")

    # 小贴士
    if tip:
        lines.append("")
        lines.append(f"小贴士：{tip}")

    return "\n".join(lines)


def _build_parent_metadata(recipe: dict, base_meta: dict) -> dict:
    """构建父文档的元数据（在基础元数据上追加额外字段）。"""
    meta = {**base_meta}
    meta["chunk_type"] = "parent"
    meta["videourl"] = recipe.get("videourl", "")
    meta["step_pics"] = recipe.get("step_pics") or []
    meta["ingredient_nutrition"] = recipe.get("ingredient_nutrition") or []
    meta["nutrition_summary"] = recipe.get("nutrition_summary") or {}
    return meta


# =========================================================================
# 子块构建
# =========================================================================

def _build_info_text(recipe: dict) -> str:
    """构建 info 子块文本（匹配分类/难度/描述类查询）。"""
    title = recipe.get("title", "")
    zid = recipe.get("zid", "")
    difficulty = recipe.get("difficulty", 3)
    difficulty_text = DIFFICULTY_MAP.get(difficulty, "未知")
    costtime = recipe.get("costtime", "")
    desc = recipe.get("desc", "")
    tags = recipe.get("tags") or []

    parts = [f"{title}，{zid}分类，{difficulty_text}难度，耗时{costtime}。"]
    if desc:
        parts.append(f"{desc}。")
    if tags:
        parts.append(f"标签：{'，'.join(tags)}")

    return "".join(parts)


def _build_ingredient_text(recipe: dict) -> str:
    """构建 ingredient 子块文本（匹配食材/营养类查询）。"""
    title = recipe.get("title", "")
    raw = recipe.get("ingredients_raw") or []
    nutrition_tags = recipe.get("nutrition_tags") or []
    main_items = _get_main_nutrition_items(recipe)

    parts = [f"{title}的食材：{'，'.join(raw)}。"]

    if nutrition_tags:
        parts.append(f"营养特点：{'，'.join(nutrition_tags)}。")

    if main_items:
        energies = [
            item["energy"] for item in main_items
            if item.get("energy") is not None
        ]
        if energies:
            min_e = min(energies)
            max_e = max(energies)
            parts.append(f"主要食材热量范围：{min_e}-{max_e}kcal/100g。")

    return "".join(parts)


def _build_step_text(recipe: dict) -> str:
    """构建 step 子块文本（匹配做法/技巧类查询）。"""
    title = recipe.get("title", "")
    steps = recipe.get("steps") or []
    step_count = recipe.get("step_count", len(steps))
    tip = recipe.get("tip", "")

    # 取前3步
    shown_steps = steps[:3]
    step_str = "；".join(shown_steps)

    parts = [f"{title}的做法：{step_str}"]

    if step_count > 3:
        parts.append(f"...共{step_count}步。")
    elif step_str:
        parts.append("。")

    if tip:
        tip_short = tip[:100]
        parts.append(f"小贴士：{tip_short}")

    return "".join(parts)


# =========================================================================
# 主接口
# =========================================================================

def build_parent_child_nodes(recipe: dict) -> dict:
    """
    构建单个食谱的父子文档节点。

    参数:
        recipe: 富化后的食谱字典（包含营养字段）

    返回:
        {
            "parent": {"text": str, "metadata": dict},
            "children": [
                {"text": str, "metadata": dict, "chunk_type": "info"},
                {"text": str, "metadata": dict, "chunk_type": "ingredient"},
                {"text": str, "metadata": dict, "chunk_type": "step"},
            ]
        }
    """
    base_meta = _build_base_metadata(recipe)

    # 父文档
    parent_text = _build_parent_text(recipe)
    parent_meta = _build_parent_metadata(recipe, base_meta)

    # 子块
    children = []
    for chunk_type, build_fn in [
        ("info", _build_info_text),
        ("ingredient", _build_ingredient_text),
        ("step", _build_step_text),
    ]:
        child_meta = {**base_meta, "chunk_type": chunk_type}
        children.append({
            "text": build_fn(recipe),
            "metadata": child_meta,
            "chunk_type": chunk_type,
        })

    return {
        "parent": {"text": parent_text, "metadata": parent_meta},
        "children": children,
    }


def build_all_nodes(recipes: list[dict]) -> list[dict]:
    """
    批量构建所有食谱的父子文档节点。

    参数:
        recipes: 富化后的食谱字典列表

    返回:
        [build_parent_child_nodes(r) for r in recipes]
    """
    return [build_parent_child_nodes(r) for r in recipes]
