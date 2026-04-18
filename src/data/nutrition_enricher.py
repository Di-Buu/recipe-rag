"""
营养预计算模块

遍历清洗后的食谱数据，对每个食材调用 NutritionMatcher 获取营养信息，
汇总为食谱级营养数据并生成定性标签。

输入: recipes_clean.json
输出: recipes_enriched.json（原始字段 + 新增营养字段）
"""

import json
import time
from pathlib import Path
from typing import Optional

from src.config import (
    CLEAN_DATA_PATH,
    ENRICHED_DATA_PATH,
    NUTRITION_DB_PATH,
    NUTRITION_COVERAGE_THRESHOLD,
    NUTRITION_COVERAGE_PARTIAL,
    NUTRITION_TAG_RULES,
)
from src.data.nutrition_matcher import NutritionMatcher, NutritionInfo


def _determine_match_type(info: NutritionInfo) -> str:
    """
    根据 NutritionInfo 的 id 和 match_score 判断匹配类型标识。

    规则：
        id == -1            → "seasoning"（调味品/零营养）
        id == -2            → "combo"（组合词拆分）
        id == -3            → "manual"（手工补充数据）
        id > 0, score == 100 → "exact"（精确匹配）
        id > 0, score >= 90  → "contains"（包含/后缀匹配）
        id > 0, score < 90   → "fuzzy"（模糊匹配）
    """
    if info.id == -1:
        return "seasoning"
    if info.id == -2:
        return "combo"
    if info.id == -3:
        return "manual"
    # id > 0: 数据库匹配
    if info.match_score == 100:
        return "exact"
    if info.match_score >= 90:
        return "contains"
    return "fuzzy"


def _build_ingredient_nutrition(
    ingredient_name: str, info: Optional[NutritionInfo]
) -> Optional[dict]:
    """
    将单个食材的匹配结果转为字典。
    未匹配（info 为 None）返回 None。
    """
    if info is None:
        return None
    return {
        "name": ingredient_name,
        "matched_name": info.name,
        "energy": info.energy,
        "protein": info.protein,
        "fat": info.fat,
        "carbs": info.carbs,
        "match_score": info.match_score,
        "match_type": _determine_match_type(info),
    }


def _compute_nutrition_summary(ingredient_nutrition: list[dict]) -> dict:
    """
    计算主食材（排除调味品）的营养均值。

    仅对 match_type != "seasoning" 的食材取平均。
    若无有效主食材，返回全零字典。
    """
    main_items = [
        item for item in ingredient_nutrition if item["match_type"] != "seasoning"
    ]
    if not main_items:
        return {"energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}

    n = len(main_items)
    return {
        "energy": round(sum(item["energy"] for item in main_items) / n, 1),
        "protein": round(sum(item["protein"] for item in main_items) / n, 1),
        "fat": round(sum(item["fat"] for item in main_items) / n, 1),
        "carbs": round(sum(item["carbs"] for item in main_items) / n, 1),
    }


def _generate_nutrition_tags(summary: dict) -> list[str]:
    """
    根据 NUTRITION_TAG_RULES 和营养均值生成定性标签。

    每条规则包含 field、op（">=" 或 "<="）、value 三个字段。
    """
    tags = []
    for tag_name, rule in NUTRITION_TAG_RULES.items():
        field_value = summary.get(rule["field"], 0.0)
        threshold = rule["value"]
        op = rule["op"]
        if op == ">=" and field_value >= threshold:
            tags.append(tag_name)
        elif op == "<=" and field_value <= threshold:
            tags.append(tag_name)
    return tags


def _determine_confidence(coverage: float) -> str:
    """
    根据覆盖率确定置信度等级。

    coverage >= NUTRITION_COVERAGE_THRESHOLD (0.8) → "high"
    coverage >= NUTRITION_COVERAGE_PARTIAL  (0.5) → "partial"
    coverage < 0.5                                → "low"
    """
    if coverage >= NUTRITION_COVERAGE_THRESHOLD:
        return "high"
    if coverage >= NUTRITION_COVERAGE_PARTIAL:
        return "partial"
    return "low"


def enrich_recipe(
    recipe: dict, matcher: NutritionMatcher
) -> dict:
    """
    对单条食谱进行营养增强。

    Args:
        recipe: 清洗后的食谱字典（需含 ingredients_clean 字段）
        matcher: NutritionMatcher 实例

    Returns:
        增强后的食谱字典（原始字段 + 营养字段）
    """
    enriched = dict(recipe)
    ingredients = recipe.get("ingredients_clean", [])

    if not ingredients:
        enriched["ingredient_nutrition"] = []
        enriched["nutrition_coverage"] = 0.0
        enriched["nutrition_summary"] = {
            "energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0
        }
        enriched["nutrition_tags"] = []
        enriched["nutrition_confidence"] = "low"
        return enriched

    # 逐食材匹配
    ingredient_nutrition = []
    matched_count = 0
    total_valid = 0

    for name in ingredients:
        name = name.strip()
        if not name:
            continue
        total_valid += 1
        info = matcher.match(name)
        entry = _build_ingredient_nutrition(name, info)
        if entry is not None:
            ingredient_nutrition.append(entry)
            matched_count += 1

    coverage = matched_count / total_valid if total_valid > 0 else 0.0
    confidence = _determine_confidence(coverage)

    # 计算主食材营养均值
    summary = _compute_nutrition_summary(ingredient_nutrition)

    # 营养标签（仅 high/partial 且有主食材时才生成，避免全调味品时产生虚假标签）
    has_main_items = any(
        item["match_type"] != "seasoning" for item in ingredient_nutrition
    )
    if confidence in ("high", "partial") and has_main_items:
        tags = _generate_nutrition_tags(summary)
    else:
        tags = []

    enriched["ingredient_nutrition"] = ingredient_nutrition
    enriched["nutrition_coverage"] = round(coverage, 4)
    enriched["nutrition_summary"] = summary
    enriched["nutrition_tags"] = tags
    enriched["nutrition_confidence"] = confidence
    return enriched


def enrich_all(
    recipes_path: Path = None,
    db_path: Path = None,
    output_path: Path = None,
    progress_interval: int = 5000,
) -> dict:
    """
    批量增强全部食谱并写入输出文件。

    Args:
        recipes_path: 清洗后食谱路径，默认 CLEAN_DATA_PATH
        db_path: 营养数据库路径，默认 NUTRITION_DB_PATH
        output_path: 输出路径，默认 ENRICHED_DATA_PATH
        progress_interval: 每处理多少条打印一次进度

    Returns:
        统计字典
    """
    recipes_path = recipes_path or CLEAN_DATA_PATH
    db_path = db_path or NUTRITION_DB_PATH
    output_path = output_path or ENRICHED_DATA_PATH

    print(f"[读取食谱] {recipes_path}")
    with open(recipes_path, "r", encoding="utf-8") as f:
        recipes = json.load(f)
    total = len(recipes)
    print(f"[食谱总数] {total:,}")

    print(f"[初始化匹配器] {db_path}")
    matcher = NutritionMatcher(db_path)

    # 统计变量
    coverage_sum = 0.0
    confidence_counts = {"high": 0, "partial": 0, "low": 0}
    tag_counts = {}

    enriched_recipes = []
    start_time = time.time()

    for i, recipe in enumerate(recipes):
        enriched = enrich_recipe(recipe, matcher)
        enriched_recipes.append(enriched)

        # 累加统计
        coverage_sum += enriched["nutrition_coverage"]
        confidence_counts[enriched["nutrition_confidence"]] += 1
        for tag in enriched["nutrition_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if (i + 1) % progress_interval == 0:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            print(
                f"  [{i + 1:,}/{total:,}] "
                f"已耗时 {elapsed:.1f}s, 速度 {speed:.0f} 条/s"
            )

    elapsed = time.time() - start_time
    avg_coverage = coverage_sum / total if total > 0 else 0.0

    # 写入输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[写入输出] {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched_recipes, f, ensure_ascii=False, indent=None)

    stats = {
        "total_recipes": total,
        "avg_coverage": round(avg_coverage, 4),
        "confidence_counts": confidence_counts,
        "tag_counts": tag_counts,
        "elapsed_seconds": round(elapsed, 1),
    }
    return stats
