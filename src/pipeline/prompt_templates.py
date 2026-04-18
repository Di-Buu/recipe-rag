"""
Prompt 模板模块

职责：定义 RAG 生成阶段使用的中文 Prompt 模板
- 食谱推荐 Prompt（通用）
- 约束感知 Prompt（处理饮食限制）
- 弱结果 Prompt（检索不足时诚实告知）
"""


def build_system_prompt() -> str:
    """构建系统级 Prompt（角色定义）。"""
    return (
        "你是一个专业的中文食谱推荐助手。"
        "你的任务是根据用户的需求，从检索到的食谱知识库中推荐最合适的菜谱。\n"
        "你必须遵守以下规则：\n"
        "1. 仅基于提供的食谱信息回答，不要编造不存在的食谱\n"
        "2. 推荐时包含：菜名、核心食材、关键步骤概括、营养特点（如有）\n"
        "3. 如果用户有饮食限制，严格遵守，不推荐含禁忌食材的菜谱\n"
        "4. 如果检索结果与需求不相关，诚实告知并给出建议\n"
        "5. 回答使用中文，语气亲切自然\n"
        "6. 不要在结尾添加互动性话语（如\"有需要可以随时问我\"\"希望对你有帮助\"等），直接结束推荐内容即可\n"
        "7. 每道推荐菜谱之间留出段落间隔，保持排版清晰易读"
    )


def build_qa_prompt(context: str, query: str, constraints: str = "") -> str:
    """
    构建食谱推荐 QA Prompt。

    参数:
        context: 检索到的父文档文本（多个食谱拼接）
        query: 用户的自然语言问题
        constraints: 用户的饮食约束描述（可选）

    返回:
        完整的 Prompt 字符串
    """
    parts = []

    parts.append("## 检索到的食谱信息\n")
    parts.append(context)
    parts.append("\n")

    if constraints:
        parts.append("## 用户的饮食约束\n")
        parts.append(constraints)
        parts.append("\n")

    parts.append("## 回答要求\n")
    parts.append(
        "1. 从上述食谱中选择最符合用户需求的进行推荐\n"
        "2. 每道推荐菜谱请包含：菜名、主要食材、简要做法、营养特点\n"
        "3. 说明推荐理由，解释为什么这道菜适合用户\n"
        "4. 如果有饮食约束，明确说明推荐菜谱如何满足约束\n"
        "5. 推荐数量控制在 3-5 道\n"
    )

    parts.append("## 用户问题\n")
    parts.append(query)

    return "\n".join(parts)


def build_weak_result_prompt(context: str, query: str) -> str:
    """
    构建弱检索结果 Prompt（当检索相关性不高时使用）。

    参数:
        context: 检索到的文本（可能相关性较低）
        query: 用户问题
    """
    parts = [
        "## 检索到的食谱信息（相关性可能不高）\n",
        context,
        "\n",
        "## 回答要求\n",
        "检索到的食谱与用户需求的匹配度可能不高。请：\n"
        "1. 诚实告知用户当前检索结果可能不完全匹配\n"
        "2. 从中挑选最接近的食谱进行推荐（如有）\n"
        "3. 给出改进搜索的建议（如更换关键词、放宽条件）\n",
        "\n## 用户问题\n",
        query,
    ]
    return "\n".join(parts)


def format_context(parent_docs: list[dict], top_k: int = 5) -> str:
    """
    将去重后的父文档列表格式化为 Prompt 上下文。

    参数:
        parent_docs: 父文档列表，每项 {"text": str, "metadata": dict, "relevance": float}
        top_k: 最多使用几个父文档

    返回:
        格式化后的上下文字符串
    """
    if not parent_docs:
        return "（未检索到相关食谱）"

    sections = []
    for i, doc in enumerate(parent_docs[:top_k], 1):
        title = doc.get("metadata", {}).get("title", "未知菜谱")
        relevance = doc.get("relevance", 0)
        sections.append(f"### 食谱 {i}：{title}（相关度：{relevance:.2f}）\n")
        sections.append(doc.get("text", ""))
        sections.append("\n---\n")

    return "\n".join(sections)


def format_constraints(filters: dict | None) -> str:
    """
    将结构化过滤条件格式化为自然语言约束描述。

    参数:
        filters: 结构化过滤条件，如：
            {
                "nutrition_tags": ["低脂"],
                "exclude_ingredients": ["花生", "虾"],
                "difficulty_max": 3,
                "costtime_max": 30,
                "categories": ["肉类", "川菜"],
                "keywords": ["家常菜"],
            }

    返回:
        自然语言描述字符串
    """
    if not filters:
        return ""

    parts = []

    if filters.get("nutrition_tags"):
        tags = "、".join(filters["nutrition_tags"])
        parts.append(f"营养偏好：{tags}")

    if filters.get("exclude_ingredients"):
        excluded = "、".join(filters["exclude_ingredients"])
        parts.append(f"食材禁忌：不能含有{excluded}")

    if filters.get("include_ingredients"):
        included = "、".join(filters["include_ingredients"])
        parts.append(f"必须包含食材：{included}")

    if filters.get("difficulty_max") is not None:
        diff_map = {0: "简单", 1: "一般", 2: "较难", 3: "困难"}
        d = filters["difficulty_max"]
        parts.append(f"难度要求：不超过{diff_map.get(d, str(d))}")

    if filters.get("costtime_max"):
        parts.append(f"时间要求：不超过{filters['costtime_max']}分钟")

    if filters.get("categories"):
        cats = "、".join(filters["categories"])
        parts.append(f"分类偏好：{cats}")

    if filters.get("keywords"):
        kws = "、".join(filters["keywords"])
        parts.append(f"关键词：{kws}")

    return "；".join(parts) if parts else ""
