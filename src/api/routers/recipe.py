"""
食谱数据路由

提供食谱详情查询、随机推荐、筛选选项等接口。
数据来源为启动时加载到 app.state.recipes 的内存字典。
"""

import random
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.schemas import (
    DIFFICULTY_MAP,
    FilterOptions,
    RecipeCard,
    RecipeDetail,
)
from src.api.dependencies import get_current_user, get_recipes
from src.utils.text_cleaner import clean_recipe_detail

router = APIRouter(prefix="/api", tags=["食谱"])


def _build_recipe_detail(raw: dict) -> dict:
    """将原始食谱数据转换为 RecipeDetail 所需字段"""
    return {
        "did": str(raw.get("did", "")),
        "title": raw.get("title", ""),
        "category": raw.get("zid", ""),
        "tags": raw.get("tags", []),
        "desc": raw.get("desc", ""),
        "difficulty": raw.get("difficulty", 0),
        "difficulty_text": DIFFICULTY_MAP.get(raw.get("difficulty", 0), "未知"),
        "costtime": raw.get("costtime", ""),
        "tip": raw.get("tip", ""),
        "ingredients_raw": raw.get("ingredients_raw", []),
        "quantities": raw.get("quantities", []),
        "steps": raw.get("steps", []),
        "step_pics": raw.get("step_pics", []),
        "thumb": raw.get("thumb", ""),
        "videourl": raw.get("videourl", ""),
        "viewnum": raw.get("viewnum", 0),
        "favnum": raw.get("favnum", 0),
        "ingredient_nutrition": raw.get("ingredient_nutrition", []),
        "nutrition_summary": raw.get("nutrition_summary"),
        "nutrition_tags": raw.get("nutrition_tags", []),
        "nutrition_coverage": raw.get("nutrition_coverage", 0.0),
    }


def _build_recipe_card(raw: dict) -> dict:
    """将原始食谱数据转换为 RecipeCard 所需字段"""
    desc = raw.get("desc", "") or ""
    return {
        "did": str(raw.get("did", "")),
        "title": raw.get("title", ""),
        "category": raw.get("zid", ""),
        "difficulty": raw.get("difficulty", 0),
        "difficulty_text": DIFFICULTY_MAP.get(raw.get("difficulty", 0), "未知"),
        "costtime": raw.get("costtime", ""),
        "thumb": raw.get("thumb", ""),
        "viewnum": raw.get("viewnum", 0),
        "favnum": raw.get("favnum", 0),
        "nutrition_tags": raw.get("nutrition_tags", []),
        "desc_preview": desc[:50],
    }


@router.get("/recipe/{recipe_id}", response_model=RecipeDetail)
async def get_recipe(
    recipe_id: str,
    current_user: dict = Depends(get_current_user),
    recipes: dict = Depends(get_recipes),
):
    """获取食谱详情

    根据食谱 ID 返回完整的食谱信息，包括食材、步骤、营养数据等。
    """
    raw = recipes.get(recipe_id)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"食谱 {recipe_id} 不存在",
        )
    return clean_recipe_detail(_build_recipe_detail(raw))


@router.get("/recipes/random", response_model=list[RecipeCard])
async def random_recipes(
    count: int = Query(default=6, ge=1, le=20, description="随机抽取数量，默认6，最大20"),
    current_user: dict = Depends(get_current_user),
    recipes: dict = Depends(get_recipes),
):
    """随机推荐食谱

    从所有食谱中随机抽取指定数量的食谱，返回卡片信息列表。
    """
    all_recipes = list(recipes.values())
    sample_size = min(count, len(all_recipes))
    sampled = random.sample(all_recipes, sample_size)
    return [_build_recipe_card(r) for r in sampled]


@router.get("/filters/options", response_model=FilterOptions)
async def filter_options(
    current_user: dict = Depends(get_current_user),
    recipes: dict = Depends(get_recipes),
):
    """获取筛选选项

    扫描所有食谱，统计分类（来自 tags/cid）、关键词（来自 zid）、
    难度、耗时、营养标签等可选筛选项。
    """
    # 统计分类（tags，来自 cid 多级分类）和关键词（zid）
    category_counter: Counter = Counter()
    keyword_counter: Counter = Counter()
    nutrition_tag_set: set[str] = set()

    for r in recipes.values():
        for tag in r.get("tags", []):
            category_counter[tag] += 1
        zid = r.get("zid", "")
        if zid:
            keyword_counter[zid] += 1
        for tag in r.get("nutrition_tags", []):
            nutrition_tag_set.add(tag)

    # 分类按数量降序排列
    categories = [
        {"value": name, "label": name, "count": cnt}
        for name, cnt in category_counter.most_common()
    ]

    # 关键词按数量降序排列
    keywords = [
        {"value": name, "label": name, "count": cnt}
        for name, cnt in keyword_counter.most_common()
    ]

    # 难度选项
    difficulties = [
        {"value": k, "label": v}
        for k, v in DIFFICULTY_MAP.items()
    ]

    # 预定义耗时选项
    costtimes = [
        {"value": 10, "label": "≤10分钟"},
        {"value": 30, "label": "≤30分钟"},
        {"value": 60, "label": "≤1小时"},
        {"value": 120, "label": "≤2小时"},
    ]

    return FilterOptions(
        categories=categories,
        keywords=keywords,
        difficulties=difficulties,
        costtimes=costtimes,
        nutrition_tags=sorted(nutrition_tag_set),
    )
