"""
营养预计算模块（nutrition_enricher）单元测试

测试内容：
1. 单食谱营养计算
2. 营养标签生成逻辑
3. 置信度分级
4. 调味品排除逻辑
5. 边界情况（空食材列表、全部未匹配等）
"""

import pytest
from unittest.mock import MagicMock, patch
from src.data.nutrition_matcher import NutritionInfo
from src.data.nutrition_enricher import (
    _determine_match_type,
    _build_ingredient_nutrition,
    _compute_nutrition_summary,
    _generate_nutrition_tags,
    _determine_confidence,
    enrich_recipe,
)


# =========================================================================
# 测试辅助：构造 NutritionInfo 实例
# =========================================================================

def _make_info(
    id: int = 1, name: str = "测试食材",
    energy: float = 100.0, protein: float = 10.0,
    fat: float = 5.0, carbs: float = 20.0,
    match_score: float = 100,
) -> NutritionInfo:
    return NutritionInfo(
        id=id, name=name,
        energy=energy, protein=protein, fat=fat, carbs=carbs,
        match_score=match_score,
    )


def _make_matcher_side_effect(mapping: dict):
    """
    构造 matcher.match 的 side_effect 函数。
    mapping: {食材名: NutritionInfo 或 None}
    """
    def side_effect(name):
        return mapping.get(name.strip())
    return side_effect


# =========================================================================
# 1. 匹配类型判定
# =========================================================================

class TestDetermineMatchType:

    def test_seasoning(self):
        info = _make_info(id=-1)
        assert _determine_match_type(info) == "seasoning"

    def test_combo(self):
        info = _make_info(id=-2)
        assert _determine_match_type(info) == "combo"

    def test_manual(self):
        info = _make_info(id=-3)
        assert _determine_match_type(info) == "manual"

    def test_exact(self):
        info = _make_info(id=42, match_score=100)
        assert _determine_match_type(info) == "exact"

    def test_contains(self):
        info = _make_info(id=42, match_score=95)
        assert _determine_match_type(info) == "contains"

    def test_contains_boundary(self):
        info = _make_info(id=42, match_score=90)
        assert _determine_match_type(info) == "contains"

    def test_fuzzy(self):
        info = _make_info(id=42, match_score=75)
        assert _determine_match_type(info) == "fuzzy"


# =========================================================================
# 2. 单食材结果构建
# =========================================================================

class TestBuildIngredientNutrition:

    def test_matched(self):
        info = _make_info(id=10, name="鸡蛋", energy=144.0, protein=13.3,
                          fat=8.8, carbs=2.8, match_score=100)
        result = _build_ingredient_nutrition("鸡蛋", info)
        assert result["name"] == "鸡蛋"
        assert result["matched_name"] == "鸡蛋"
        assert result["energy"] == 144.0
        assert result["match_type"] == "exact"

    def test_unmatched(self):
        result = _build_ingredient_nutrition("不存在", None)
        assert result is None


# =========================================================================
# 3. 营养均值计算（排除调味品）
# =========================================================================

class TestComputeNutritionSummary:

    def test_excludes_seasoning(self):
        """调味品应被排除"""
        items = [
            {"name": "鸡蛋", "match_type": "exact",
             "energy": 144, "protein": 13, "fat": 9, "carbs": 3},
            {"name": "水", "match_type": "seasoning",
             "energy": 0, "protein": 0, "fat": 0, "carbs": 0},
        ]
        summary = _compute_nutrition_summary(items)
        assert summary["energy"] == 144.0
        assert summary["protein"] == 13.0

    def test_average(self):
        """多个主食材取均值"""
        items = [
            {"name": "A", "match_type": "exact",
             "energy": 100, "protein": 10, "fat": 4, "carbs": 20},
            {"name": "B", "match_type": "manual",
             "energy": 200, "protein": 20, "fat": 6, "carbs": 40},
        ]
        summary = _compute_nutrition_summary(items)
        assert summary["energy"] == 150.0
        assert summary["protein"] == 15.0
        assert summary["fat"] == 5.0
        assert summary["carbs"] == 30.0

    def test_empty(self):
        summary = _compute_nutrition_summary([])
        assert summary == {"energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}

    def test_all_seasonings(self):
        """全部为调味品时，返回全零"""
        items = [
            {"name": "水", "match_type": "seasoning",
             "energy": 0, "protein": 0, "fat": 0, "carbs": 0},
        ]
        summary = _compute_nutrition_summary(items)
        assert summary == {"energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}

    def test_combo_included(self):
        """组合词（id=-2）应参与计算"""
        items = [
            {"name": "葱姜蒜", "match_type": "combo",
             "energy": 50, "protein": 2, "fat": 0.5, "carbs": 8},
        ]
        summary = _compute_nutrition_summary(items)
        assert summary["energy"] == 50.0


# =========================================================================
# 4. 营养标签生成
# =========================================================================

class TestGenerateNutritionTags:

    def test_high_protein(self):
        summary = {"energy": 200, "protein": 20, "fat": 10, "carbs": 5}
        tags = _generate_nutrition_tags(summary)
        assert "高蛋白" in tags
        assert "低脂" not in tags

    def test_low_fat(self):
        summary = {"energy": 200, "protein": 5, "fat": 3, "carbs": 10}
        tags = _generate_nutrition_tags(summary)
        assert "低脂" in tags

    def test_low_calorie(self):
        summary = {"energy": 80, "protein": 5, "fat": 2, "carbs": 10}
        tags = _generate_nutrition_tags(summary)
        assert "低卡" in tags

    def test_high_carbs(self):
        summary = {"energy": 350, "protein": 8, "fat": 1, "carbs": 75}
        tags = _generate_nutrition_tags(summary)
        assert "高碳水" in tags

    def test_multiple_tags(self):
        """低卡+低脂"""
        summary = {"energy": 50, "protein": 3, "fat": 1, "carbs": 8}
        tags = _generate_nutrition_tags(summary)
        assert "低卡" in tags
        assert "低脂" in tags

    def test_no_tags(self):
        """中等营养，不触发任何标签"""
        summary = {"energy": 200, "protein": 10, "fat": 10, "carbs": 30}
        tags = _generate_nutrition_tags(summary)
        assert tags == []

    def test_boundary_high_protein(self):
        """边界：protein 恰好 == 15"""
        summary = {"energy": 200, "protein": 15.0, "fat": 10, "carbs": 30}
        tags = _generate_nutrition_tags(summary)
        assert "高蛋白" in tags

    def test_boundary_low_fat(self):
        """边界：fat 恰好 == 5"""
        summary = {"energy": 200, "protein": 10, "fat": 5.0, "carbs": 30}
        tags = _generate_nutrition_tags(summary)
        assert "低脂" in tags


# =========================================================================
# 5. 置信度分级
# =========================================================================

class TestDetermineConfidence:

    def test_high(self):
        assert _determine_confidence(0.9) == "high"

    def test_high_boundary(self):
        assert _determine_confidence(0.8) == "high"

    def test_partial(self):
        assert _determine_confidence(0.6) == "partial"

    def test_partial_boundary(self):
        assert _determine_confidence(0.5) == "partial"

    def test_low(self):
        assert _determine_confidence(0.3) == "low"

    def test_zero(self):
        assert _determine_confidence(0.0) == "low"

    def test_full(self):
        assert _determine_confidence(1.0) == "high"


# =========================================================================
# 6. 单食谱增强（enrich_recipe）
# =========================================================================

class TestEnrichRecipe:

    def _make_recipe(self, ingredients: list[str]) -> dict:
        return {
            "did": "test_001",
            "title": "测试食谱",
            "ingredients_clean": ingredients,
        }

    def test_basic_enrichment(self):
        """基本功能：3个食材全匹配"""
        recipe = self._make_recipe(["鸡蛋", "番茄", "盐"])
        mapping = {
            "鸡蛋": _make_info(id=10, name="鸡蛋", energy=144, protein=13.3,
                             fat=8.8, carbs=2.8, match_score=100),
            "番茄": _make_info(id=20, name="番茄", energy=19, protein=0.9,
                             fat=0.2, carbs=4.0, match_score=100),
            "盐": _make_info(id=30, name="精盐", energy=0, protein=0,
                           fat=0, carbs=0, match_score=100),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)

        assert result["nutrition_coverage"] == 1.0
        assert result["nutrition_confidence"] == "high"
        assert len(result["ingredient_nutrition"]) == 3
        assert result["did"] == "test_001"  # 保留原始字段

    def test_seasoning_excluded_from_summary(self):
        """调味品在营养均值中应被排除"""
        recipe = self._make_recipe(["鸡蛋", "水"])
        mapping = {
            "鸡蛋": _make_info(id=10, name="鸡蛋", energy=144, protein=13.3,
                             fat=8.8, carbs=2.8),
            "水": _make_info(id=-1, name="水", energy=0, protein=0,
                           fat=0, carbs=0),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        # 均值应只基于鸡蛋
        assert result["nutrition_summary"]["energy"] == 144.0
        assert result["nutrition_summary"]["protein"] == 13.3

    def test_partial_match(self):
        """部分匹配：2/3 匹配 → partial"""
        recipe = self._make_recipe(["鸡蛋", "番茄", "不存在食材"])
        mapping = {
            "鸡蛋": _make_info(id=10, energy=144, protein=13.3,
                             fat=8.8, carbs=2.8),
            "番茄": _make_info(id=20, energy=19, protein=0.9,
                             fat=0.2, carbs=4.0),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        assert abs(result["nutrition_coverage"] - 2 / 3) < 0.01
        assert result["nutrition_confidence"] == "partial"
        assert len(result["ingredient_nutrition"]) == 2

    def test_low_confidence_no_tags(self):
        """覆盖率 < 0.5 时，不生成标签"""
        recipe = self._make_recipe(["A", "B", "C", "D", "E"])
        mapping = {
            "A": _make_info(id=10, energy=50, protein=20, fat=1, carbs=5),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        assert result["nutrition_confidence"] == "low"
        assert result["nutrition_tags"] == []

    def test_empty_ingredients(self):
        """空食材列表"""
        recipe = self._make_recipe([])
        matcher = MagicMock()

        result = enrich_recipe(recipe, matcher)
        assert result["nutrition_coverage"] == 0.0
        assert result["nutrition_confidence"] == "low"
        assert result["ingredient_nutrition"] == []
        assert result["nutrition_tags"] == []
        # matcher 不应被调用
        matcher.match.assert_not_called()

    def test_all_unmatched(self):
        """全部未匹配"""
        recipe = self._make_recipe(["A", "B", "C"])
        matcher = MagicMock()
        matcher.match.return_value = None

        result = enrich_recipe(recipe, matcher)
        assert result["nutrition_coverage"] == 0.0
        assert result["nutrition_confidence"] == "low"
        assert result["ingredient_nutrition"] == []
        assert result["nutrition_tags"] == []

    def test_tags_generated_for_high_confidence(self):
        """高置信度时应生成标签"""
        # 5个食材全匹配，高蛋白
        recipe = self._make_recipe(["A", "B", "C", "D", "E"])
        high_protein = _make_info(
            id=10, energy=200, protein=25, fat=10, carbs=5
        )
        mapping = {name: high_protein for name in ["A", "B", "C", "D", "E"]}
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        assert result["nutrition_confidence"] == "high"
        assert "高蛋白" in result["nutrition_tags"]

    def test_combo_and_manual_included(self):
        """组合词（id=-2）和手工数据（id=-3）应参与营养计算"""
        recipe = self._make_recipe(["葱姜蒜", "八角"])
        mapping = {
            "葱姜蒜": _make_info(id=-2, name="葱姜蒜[葱+姜+蒜]",
                               energy=40, protein=2, fat=0.3, carbs=8),
            "八角": _make_info(id=-3, name="八角",
                             energy=281, protein=3.8, fat=5.6, carbs=50),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        assert result["nutrition_coverage"] == 1.0
        # 两项都参与均值计算
        assert result["nutrition_summary"]["energy"] == round((40 + 281) / 2, 1)

    def test_whitespace_ingredient_skipped(self):
        """空白食材名应跳过"""
        recipe = self._make_recipe(["鸡蛋", "  ", ""])
        mapping = {
            "鸡蛋": _make_info(id=10, energy=144, protein=13.3,
                             fat=8.8, carbs=2.8),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        # 只有1个有效食材
        assert result["nutrition_coverage"] == 1.0

    def test_all_seasonings_no_false_tags(self):
        """全调味品时不应产生虚假的低脂/低卡标签"""
        recipe = self._make_recipe(["水", "盐", "醋", "酱油", "未知食材"])
        mapping = {
            "水": _make_info(id=-1, name="水", energy=0, protein=0, fat=0, carbs=0),
            "盐": _make_info(id=-1, name="精盐", energy=0, protein=0, fat=0, carbs=0),
            "醋": _make_info(id=-1, name="醋", energy=0, protein=0, fat=0, carbs=0),
            "酱油": _make_info(id=-1, name="酱油", energy=0, protein=0, fat=0, carbs=0),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        # 4/5 匹配，coverage=0.8 → high，但全是调味品 → 不应生成标签
        assert result["nutrition_confidence"] == "high"
        assert result["nutrition_tags"] == []

    def test_preserves_original_fields(self):
        """增强后应保留原始食谱的所有字段"""
        recipe = {
            "did": "12345",
            "title": "红烧肉",
            "tags": ["下饭菜"],
            "ingredients_clean": ["猪肉"],
            "custom_field": "自定义",
        }
        mapping = {
            "猪肉": _make_info(id=10, name="猪肉", energy=395, protein=13.2,
                             fat=37, carbs=2.4),
        }
        matcher = MagicMock()
        matcher.match.side_effect = _make_matcher_side_effect(mapping)

        result = enrich_recipe(recipe, matcher)
        assert result["did"] == "12345"
        assert result["title"] == "红烧肉"
        assert result["tags"] == ["下饭菜"]
        assert result["custom_field"] == "自定义"
