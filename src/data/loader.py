"""
食谱数据加载器

职责：
- 从 JSON 数组文件加载食谱数据（recipes_clean.json / recipes_enriched.json）
- 提供统一的加载接口

数据来源：豆果美食结构化数据（经 csv_cleaner 清洗 + nutrition_enricher 增强）
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from src.config import CLEAN_DATA_PATH, ENRICHED_DATA_PATH


def load_recipes(
    path: Path = None, limit: int = None
) -> List[Dict[str, Any]]:
    """
    加载增强后的食谱数据（含营养信息）

    优先加载 recipes_enriched.json，若不存在则回退到 recipes_clean.json。

    Args:
        path: 数据文件路径，默认自动选择
        limit: 限制加载数量（用于测试），None 表示全部加载

    Returns:
        食谱字典列表
    """
    if path is None:
        path = ENRICHED_DATA_PATH if ENRICHED_DATA_PATH.exists() else CLEAN_DATA_PATH

    with open(path, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    if limit is not None:
        recipes = recipes[:limit]

    return recipes


def load_clean_recipes(
    path: Path = None, limit: int = None
) -> List[Dict[str, Any]]:
    """
    加载清洗后的食谱数据（不含营养信息）

    Args:
        path: 数据文件路径，默认 CLEAN_DATA_PATH
        limit: 限制加载数量（用于测试），None 表示全部加载

    Returns:
        食谱字典列表
    """
    path = path or CLEAN_DATA_PATH
    with open(path, "r", encoding="utf-8") as f:
        recipes = json.load(f)

    if limit is not None:
        recipes = recipes[:limit]

    return recipes


# =============================================================================
# 以下为旧版加载器函数（基于下厨房 JSONL 格式），已废弃
# 功能已转移到 document_builder.py
# =============================================================================

def _extract_useful_keywords(keywords: List[str]) -> List[str]:
    """[已废弃] 从 keywords 中提取有效标签"""
    filter_patterns = ["的做法", "家常做法", "详细做法", "怎么做", "最正宗做法"]
    return [kw for kw in keywords if not any(p in kw for p in filter_patterns)]


def recipe_to_document(recipe: Dict[str, Any]) -> str:
    """[已废弃] 将单个食谱转换为可检索的文本文档，功能已转移到 document_builder.py"""
    parts = []

    name = recipe.get("name", "")
    dish = recipe.get("dish", "Unknown")
    dish_display = "未知" if dish == "Unknown" else dish

    # 摘要行（强化菜名语义，提升检索匹配度）
    parts.append(f"这是一道{name}的做法，属于{dish_display}类食谱。")

    # 标题
    parts.append(f"标题：{name}")

    # 菜名
    parts.append(f"菜名：{dish_display}")

    # 描述
    parts.append(f"描述：{recipe.get('description', '')}")

    # 食材（一行一个）
    ingredients = recipe.get("recipeIngredient", [])
    if ingredients:
        ingredients_lines = "\n".join(f"  - {item}" for item in ingredients)
        parts.append(f"食材：\n{ingredients_lines}")

    # 步骤（带序号，一行一步）
    instructions = recipe.get("recipeInstructions", [])
    if instructions:
        steps_lines = "\n".join(
            f"  {i}. {step}" for i, step in enumerate(instructions, 1)
        )
        parts.append(f"步骤：\n{steps_lines}")

    # 作者
    parts.append(f"作者：{recipe.get('author', '')}")

    # 来源
    parts.append("来源：下厨房")

    # 关键词
    keywords = recipe.get("keywords", [])
    useful_tags = _extract_useful_keywords(keywords)
    if useful_tags:
        parts.append(f"关键词：{' '.join(useful_tags)}")

    return "\n".join(parts)


def build_documents(recipes: List[Dict[str, Any]]) -> List[str]:
    """[已废弃] 批量将食谱转换为文档，功能已转移到 document_builder.py"""
    return [recipe_to_document(recipe) for recipe in recipes]


def build_llamaindex_documents(recipes: List[Dict[str, Any]]) -> List[Document]:
    """[已废弃] 批量将食谱转换为 LlamaIndex Document 对象，功能已转移到 document_builder.py"""
    documents = []
    for i, recipe in enumerate(recipes):
        text = recipe_to_document(recipe)
        keywords = _extract_useful_keywords(recipe.get("keywords", []))

        doc = Document(
            text=text,
            metadata={
                "name": recipe.get("name", ""),
                "dish": recipe.get("dish", ""),
                "author": recipe.get("author", ""),
                "keywords": ", ".join(keywords),
                "source": "下厨房",
            },
            doc_id=f"recipe_{i}",
        )
        documents.append(doc)
    return documents


def _build_embed_text(recipe: Dict[str, Any]) -> str:
    """[已废弃] 构建用于 embedding 的短文本"""
    name = recipe.get("name", "")
    dish = recipe.get("dish", "Unknown")
    keywords = _extract_useful_keywords(recipe.get("keywords", []))

    parts = [f"{name}的做法"]
    if dish != "Unknown" and dish != name:
        parts.append(dish)
    if keywords:
        parts.append(" ".join(keywords))
    return " ".join(parts)


def build_text_nodes(
    recipes: List[Dict[str, Any]],
    max_text_length: int = 2000,
) -> List[TextNode]:
    """[已废弃] 将食谱转换为 TextNode，功能已转移到 document_builder.py"""
    nodes = []
    for i, recipe in enumerate(recipes):
        # 短文本用于 embedding（菜名+食材+关键词）
        embed_text = _build_embed_text(recipe)

        # 完整文本用于 LLM context
        full_text = recipe_to_document(recipe)
        if len(full_text) > max_text_length:
            full_text = full_text[:max_text_length] + "\n...（内容过长已截断）"

        keywords = _extract_useful_keywords(recipe.get("keywords", []))

        node = TextNode(
            text=embed_text,
            id_=str(uuid.uuid5(uuid.NAMESPACE_URL, f"recipe_{i}")),
            metadata={
                "name": recipe.get("name", ""),
                "dish": recipe.get("dish", ""),
                "author": recipe.get("author", ""),
                "keywords": ", ".join(keywords),
                "source": "下厨房",
                "full_recipe": full_text,
            },
            # 所有 metadata 不参与 embedding（键值对格式会严重扭曲 embedding）
            # 只用 text 中的纯自然语言短文本做 embedding
            excluded_embed_metadata_keys=[
                "name", "dish", "author", "keywords", "source", "full_recipe",
            ],
            # embedding 相关的 metadata 不传给 LLM（避免重复）
            excluded_llm_metadata_keys=[
                "name", "dish", "keywords",
            ],
        )
        nodes.append(node)
    return nodes
