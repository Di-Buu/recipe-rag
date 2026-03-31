"""
食谱数据加载器

职责：
- 加载 JSONL 格式的食谱数据（每行一个 JSON）
- 将结构化数据转换为可检索的文本文档
- 提供 LlamaIndex Document 格式的输出
- 保留原始食谱索引用于结果追溯

数据来源：下厨房网页版结构化整理
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Any

from llama_index.core import Document
from llama_index.core.schema import TextNode


def load_recipes(file_path: Path, limit: int = None) -> List[Dict[str, Any]]:
    """
    从 JSONL 文件加载食谱数据

    Args:
        file_path: 数据文件路径
        limit: 限制加载数量（用于测试），None 表示全部加载

    Returns:
        食谱字典列表
    """
    recipes = []
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            recipe = json.loads(line.strip())
            recipes.append(recipe)
    return recipes


def _extract_useful_keywords(keywords: List[str]) -> List[str]:
    """
    从 keywords 中提取有效标签，过滤模板关键词

    过滤规则：删除包含以下模式的关键词
    - 的做法、家常做法、详细做法、怎么做、最正宗做法
    """
    filter_patterns = ["的做法", "家常做法", "详细做法", "怎么做", "最正宗做法"]
    return [kw for kw in keywords if not any(p in kw for p in filter_patterns)]


def recipe_to_document(recipe: Dict[str, Any]) -> str:
    """
    将单个食谱转换为可检索的文本文档

    文档格式：
        标题：<name>
        菜名：<dish>（Unknown → 未知）
        描述：<description>
        食材：一行一个
        步骤：带序号，一行一步
        作者：<author>
        来源：下厨房
        关键词：过滤模板后的有效标签

    Args:
        recipe: 食谱字典

    Returns:
        拼接后的文本文档
    """
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
    """
    批量将食谱转换为文档

    Args:
        recipes: 食谱字典列表

    Returns:
        文档字符串列表（索引与 recipes 一一对应）
    """
    return [recipe_to_document(recipe) for recipe in recipes]


def build_llamaindex_documents(recipes: List[Dict[str, Any]]) -> List[Document]:
    """
    批量将食谱转换为 LlamaIndex Document 对象

    每个 Document 包含：
    - text: 由 recipe_to_document() 生成的完整文本
    - metadata: name, dish, author, keywords（便于过滤和展示）

    Args:
        recipes: 食谱字典列表

    Returns:
        LlamaIndex Document 对象列表
    """
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
    """
    构建用于 embedding 的短文本（只含核心检索关键词）

    Qwen3-Embedding-0.6B 是轻量模型，长文本会严重稀释语义。
    经过测试，只用菜名时检索准确率最高（sim=0.56），
    加入食材/步骤后反而下降（sim=0.18-0.27）。
    """
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
    """
    将食谱直接转换为 TextNode（跳过 LlamaIndex 自动分块）

    设计策略：分离 embedding 文本和 LLM 文本
    - text: 只含菜名+食材+关键词的短文本（用于 embedding 检索）
    - metadata["full_recipe"]: 完整食谱文本（传给 LLM 生成回答）

    这样 embedding 聚焦于菜名语义，不被步骤描述稀释。

    Args:
        recipes: 食谱字典列表
        max_text_length: 单个食谱文本最大长度（超过则截断）

    Returns:
        TextNode 列表，每个节点对应一个完整食谱
    """
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
