"""prompt_templates 模块的单元测试"""

import pytest
from src.pipeline.prompt_templates import (
    build_system_prompt,
    build_qa_prompt,
    build_weak_result_prompt,
    format_context,
    format_constraints,
)


class TestBuildSystemPrompt:
    """系统 Prompt 测试"""

    def test_returns_string(self):
        result = build_system_prompt()
        assert isinstance(result, str)

    def test_contains_role_definition(self):
        result = build_system_prompt()
        assert "食谱推荐助手" in result

    def test_contains_rules(self):
        result = build_system_prompt()
        assert "不要编造" in result
        assert "饮食限制" in result
        assert "诚实告知" in result


class TestBuildQaPrompt:
    """QA Prompt 测试"""

    def test_basic_prompt(self):
        result = build_qa_prompt(context="红烧肉食谱...", query="推荐一道肉菜")
        assert "红烧肉食谱" in result
        assert "推荐一道肉菜" in result
        assert "检索到的食谱信息" in result
        assert "回答要求" in result

    def test_with_constraints(self):
        result = build_qa_prompt(
            context="蒸鱼食谱...",
            query="推荐低脂菜",
            constraints="营养偏好：低脂",
        )
        assert "饮食约束" in result
        assert "低脂" in result

    def test_without_constraints(self):
        result = build_qa_prompt(context="test", query="test")
        assert "## 用户的饮食约束" not in result

    def test_empty_context(self):
        result = build_qa_prompt(context="", query="推荐菜")
        assert "推荐菜" in result

    def test_recommendation_count(self):
        result = build_qa_prompt(context="test", query="test")
        assert "3-5" in result


class TestBuildWeakResultPrompt:
    """弱结果 Prompt 测试"""

    def test_contains_honesty_instruction(self):
        result = build_weak_result_prompt(context="不太相关的内容", query="火锅怎么做")
        assert "相关性可能不高" in result
        assert "诚实告知" in result

    def test_contains_query(self):
        result = build_weak_result_prompt(context="test", query="蒸蛋做法")
        assert "蒸蛋做法" in result

    def test_suggests_improvement(self):
        result = build_weak_result_prompt(context="test", query="test")
        assert "建议" in result


class TestFormatContext:
    """上下文格式化测试"""

    def test_empty_list(self):
        result = format_context([])
        assert "未检索到" in result

    def test_single_doc(self):
        docs = [
            {
                "text": "【红烧肉】\n分类：家常菜...",
                "metadata": {"title": "红烧肉"},
                "relevance": 0.85,
            }
        ]
        result = format_context(docs)
        assert "食谱 1：红烧肉" in result
        assert "0.85" in result
        assert "红烧肉" in result

    def test_multiple_docs(self):
        docs = [
            {"text": "菜A", "metadata": {"title": "A"}, "relevance": 0.9},
            {"text": "菜B", "metadata": {"title": "B"}, "relevance": 0.7},
            {"text": "菜C", "metadata": {"title": "C"}, "relevance": 0.5},
        ]
        result = format_context(docs)
        assert "食谱 1：A" in result
        assert "食谱 2：B" in result
        assert "食谱 3：C" in result

    def test_top_k_limit(self):
        docs = [
            {"text": f"菜{i}", "metadata": {"title": f"菜{i}"}, "relevance": 0.5}
            for i in range(10)
        ]
        result = format_context(docs, top_k=3)
        assert "食谱 3" in result
        assert "食谱 4" not in result

    def test_missing_metadata(self):
        docs = [{"text": "内容", "relevance": 0.5}]
        result = format_context(docs)
        assert "未知菜谱" in result

    def test_missing_relevance(self):
        docs = [{"text": "内容", "metadata": {"title": "菜"}}]
        result = format_context(docs)
        assert "0.00" in result


class TestFormatConstraints:
    """约束格式化测试"""

    def test_none_filters(self):
        assert format_constraints(None) == ""

    def test_empty_filters(self):
        assert format_constraints({}) == ""

    def test_nutrition_tags(self):
        result = format_constraints({"nutrition_tags": ["低脂", "高蛋白"]})
        assert "低脂" in result
        assert "高蛋白" in result
        assert "营养偏好" in result

    def test_exclude_ingredients(self):
        result = format_constraints({"exclude_ingredients": ["花生", "虾"]})
        assert "花生" in result
        assert "虾" in result
        assert "食材禁忌" in result

    def test_include_ingredients(self):
        result = format_constraints({"include_ingredients": ["鸡胸肉"]})
        assert "鸡胸肉" in result
        assert "必须包含" in result

    def test_difficulty_max(self):
        result = format_constraints({"difficulty_max": 2})
        assert "较难" in result

    def test_costtime_max(self):
        result = format_constraints({"costtime_max": 30})
        assert "30分钟" in result

    def test_category(self):
        result = format_constraints({"categories": ["川菜"]})
        assert "川菜" in result

    def test_multiple_categories(self):
        result = format_constraints({"categories": ["川菜", "粤菜"]})
        assert "川菜" in result
        assert "粤菜" in result

    def test_combined_constraints(self):
        result = format_constraints({
            "nutrition_tags": ["低脂"],
            "exclude_ingredients": ["辣椒"],
            "difficulty_max": 3,
        })
        assert "低脂" in result
        assert "辣椒" in result
        assert "困难" in result
        assert "；" in result  # 多条件分号连接
