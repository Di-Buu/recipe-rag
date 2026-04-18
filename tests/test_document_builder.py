"""
文档构建器模块（document_builder）单元测试

测试内容：
1. 父文档文本格式（标题、分类、难度、食材、营养、步骤）
2. 子块文本格式（info / ingredient / step）
3. 元数据字段完整性与正确性
4. 边界情况（空食材、空步骤、低置信度等）
5. costtime 数值化解析
6. 批量构建接口
"""

import pytest
from src.data.document_builder import (
    DIFFICULTY_MAP,
    CONFIDENCE_MAP,
    parse_costtime_minutes,
    build_parent_child_nodes,
    build_all_nodes,
)


# =========================================================================
# 测试辅助：构造完整食谱数据
# =========================================================================

def _make_recipe(**overrides) -> dict:
    """构造一条完整的测试食谱，可通过 overrides 覆盖任意字段。"""
    base = {
        "did": "1395626",
        "title": "迷迭香：干煸菜花",
        "zid": "下饭菜",
        "tags": ["下饭菜", "午餐"],
        "desc": "一道简单好吃的家常菜",
        "difficulty": 2,
        "costtime": "10-30分钟",
        "tip": "注意火候控制",
        "ingredients_raw": ["花菜", "五花肉 （切丁）", "盐"],
        "ingredients_clean": ["花菜", "五花肉", "盐"],
        "quantities": ["1颗", "3两", "适量"],
        "has_quantity": True,
        "ingredient_count": 3,
        "steps": ["1. 花菜掰成小朵", "2. 五花肉切丁"],
        "step_count": 2,
        "step_pics": ["http://pic1.jpg"],
        "thumb": "http://thumb.jpg",
        "videourl": "",
        "viewnum": 68286,
        "favnum": 2920,
        "ingredient_nutrition": [
            {
                "name": "花菜", "matched_name": "菜花",
                "energy": 23.0, "protein": 2.1, "fat": 0.2, "carbs": 4.6,
                "match_score": 100, "match_type": "alias",
            },
            {
                "name": "五花肉", "matched_name": "猪肉(肥瘦)",
                "energy": 395.0, "protein": 13.2, "fat": 37.0, "carbs": 2.4,
                "match_score": 90, "match_type": "contains",
            },
            {
                "name": "盐", "matched_name": "精盐",
                "energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0,
                "match_score": 100, "match_type": "seasoning",
            },
        ],
        "nutrition_coverage": 1.0,
        "nutrition_summary": {
            "energy": 209.0, "protein": 7.7, "fat": 18.6, "carbs": 3.5,
        },
        "nutrition_tags": ["高蛋白"],
        "nutrition_confidence": "high",
    }
    base.update(overrides)
    return base


# =========================================================================
# 一、costtime 数值化测试
# =========================================================================

class TestParseCosttimeMinutes:
    """costtime 文本 → 分钟数解析。"""

    def test_range_minutes(self):
        assert parse_costtime_minutes("10-30分钟") == 20

    def test_range_minutes_30_60(self):
        assert parse_costtime_minutes("30-60分钟") == 45

    def test_around_minutes(self):
        assert parse_costtime_minutes("10分钟左右") == 10

    def test_over_one_hour(self):
        assert parse_costtime_minutes("1小时以上") == 90

    def test_hour_range(self):
        assert parse_costtime_minutes("1-2小时") == 90

    def test_days(self):
        assert parse_costtime_minutes("数天") == 1440

    def test_empty_string(self):
        assert parse_costtime_minutes("") is None

    def test_none_input(self):
        assert parse_costtime_minutes(None) is None

    def test_whitespace_only(self):
        assert parse_costtime_minutes("   ") is None


# =========================================================================
# 二、父文档文本测试
# =========================================================================

class TestParentText:
    """父文档文本格式验证。"""

    def test_title_in_text(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "【迷迭香：干煸菜花】" in text

    def test_category_difficulty(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "分类：下饭菜" in text
        assert "难度：较难" in text
        assert "耗时：10-30分钟" in text

    def test_desc_present(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "描述：一道简单好吃的家常菜" in text

    def test_desc_empty_not_output(self):
        result = build_parent_child_nodes(_make_recipe(desc=""))
        text = result["parent"]["text"]
        assert "描述：" not in text

    def test_ingredient_list_format(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "- 花菜 1颗" in text
        assert "- 五花肉 （切丁） 3两" in text
        assert "- 盐 适量" in text

    def test_ingredient_no_quantity(self):
        """没有 quantities 时只显示食材名。"""
        result = build_parent_child_nodes(_make_recipe(quantities=[]))
        text = result["parent"]["text"]
        assert "- 花菜" in text
        assert "- 五花肉 （切丁）" in text
        # 不应拼接额外空格
        assert "- 花菜 " not in text or "- 花菜\n" in text

    def test_nutrition_high_confidence(self):
        """high 置信度时显示营养概况。"""
        result = build_parent_child_nodes(_make_recipe(nutrition_confidence="high"))
        text = result["parent"]["text"]
        assert "营养概况（每100g均值）：" in text
        assert "热量 209.0kcal" in text
        assert "蛋白质 7.7g" in text
        assert "（置信度：可靠）" in text

    def test_nutrition_partial_confidence(self):
        """partial 置信度时也显示营养概况。"""
        result = build_parent_child_nodes(
            _make_recipe(nutrition_confidence="partial")
        )
        text = result["parent"]["text"]
        assert "营养概况（每100g均值）：" in text
        assert "（置信度：仅供参考）" in text

    def test_nutrition_low_confidence_hidden(self):
        """low 置信度时不显示营养概况。"""
        result = build_parent_child_nodes(
            _make_recipe(nutrition_confidence="low")
        )
        text = result["parent"]["text"]
        assert "营养概况" not in text

    def test_steps_present(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "做法步骤：" in text
        assert "1. 花菜掰成小朵" in text
        assert "2. 五花肉切丁" in text

    def test_tip_present(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "小贴士：注意火候控制" in text

    def test_tip_empty_not_output(self):
        result = build_parent_child_nodes(_make_recipe(tip=""))
        text = result["parent"]["text"]
        assert "小贴士" not in text

    def test_nutrition_tags_display(self):
        result = build_parent_child_nodes(_make_recipe())
        text = result["parent"]["text"]
        assert "营养标签：高蛋白" in text


# =========================================================================
# 三、子块文本测试
# =========================================================================

class TestInfoChunk:
    """info 子块文本验证。"""

    def test_contains_category_and_difficulty(self):
        result = build_parent_child_nodes(_make_recipe())
        info = result["children"][0]
        assert info["chunk_type"] == "info"
        assert "下饭菜分类" in info["text"]
        assert "较难难度" in info["text"]

    def test_contains_desc(self):
        result = build_parent_child_nodes(_make_recipe())
        info = result["children"][0]
        assert "一道简单好吃的家常菜" in info["text"]

    def test_contains_tags(self):
        result = build_parent_child_nodes(_make_recipe())
        info = result["children"][0]
        assert "标签：下饭菜，午餐" in info["text"]

    def test_empty_desc(self):
        result = build_parent_child_nodes(_make_recipe(desc=""))
        info = result["children"][0]
        # 不应出现连续的句号
        assert "。。" not in info["text"]

    def test_empty_tags(self):
        result = build_parent_child_nodes(_make_recipe(tags=[]))
        info = result["children"][0]
        assert "标签" not in info["text"]


class TestIngredientChunk:
    """ingredient 子块文本验证。"""

    def test_contains_ingredients(self):
        result = build_parent_child_nodes(_make_recipe())
        ingr = result["children"][1]
        assert ingr["chunk_type"] == "ingredient"
        assert "花菜" in ingr["text"]
        assert "五花肉" in ingr["text"]

    def test_contains_nutrition_tags(self):
        result = build_parent_child_nodes(_make_recipe())
        ingr = result["children"][1]
        assert "营养特点：高蛋白" in ingr["text"]

    def test_empty_nutrition_tags(self):
        result = build_parent_child_nodes(_make_recipe(nutrition_tags=[]))
        ingr = result["children"][1]
        assert "营养特点" not in ingr["text"]

    def test_energy_range_excludes_seasoning(self):
        """热量范围排除调味品。"""
        result = build_parent_child_nodes(_make_recipe())
        ingr = result["children"][1]
        # 花菜=23, 五花肉=395, 盐被排除
        assert "23.0-395.0kcal/100g" in ingr["text"]

    def test_no_main_ingredients_no_energy_range(self):
        """所有食材都是调味品时不显示热量范围。"""
        recipe = _make_recipe(
            ingredient_nutrition=[
                {
                    "name": "盐", "matched_name": "精盐",
                    "energy": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0,
                    "match_score": 100, "match_type": "seasoning",
                },
            ],
        )
        result = build_parent_child_nodes(recipe)
        ingr = result["children"][1]
        assert "热量范围" not in ingr["text"]


class TestStepChunk:
    """step 子块文本验证。"""

    def test_contains_steps(self):
        result = build_parent_child_nodes(_make_recipe())
        step = result["children"][2]
        assert step["chunk_type"] == "step"
        assert "1. 花菜掰成小朵" in step["text"]
        assert "2. 五花肉切丁" in step["text"]

    def test_less_than_3_steps_no_total(self):
        """步骤 <=3 时不显示"共X步"。"""
        result = build_parent_child_nodes(_make_recipe())
        step = result["children"][2]
        assert "共" not in step["text"]

    def test_more_than_3_steps_show_total(self):
        """步骤 >3 时显示"...共X步"。"""
        recipe = _make_recipe(
            steps=[
                "1. 第一步", "2. 第二步", "3. 第三步",
                "4. 第四步", "5. 第五步",
            ],
            step_count=5,
        )
        result = build_parent_child_nodes(recipe)
        step = result["children"][2]
        assert "共5步" in step["text"]
        # 只显示前3步
        assert "4. 第四步" not in step["text"]

    def test_tip_in_step_chunk(self):
        result = build_parent_child_nodes(_make_recipe())
        step = result["children"][2]
        assert "小贴士：注意火候控制" in step["text"]

    def test_tip_empty_not_in_step(self):
        result = build_parent_child_nodes(_make_recipe(tip=""))
        step = result["children"][2]
        assert "小贴士" not in step["text"]

    def test_long_tip_truncated(self):
        """tip 超过100字时截断。"""
        long_tip = "这是一个非常长的小贴士" * 20  # 远超100字
        recipe = _make_recipe(tip=long_tip)
        result = build_parent_child_nodes(recipe)
        step = result["children"][2]
        # step 子块中的 tip 应不超过100字
        tip_part = step["text"].split("小贴士：")[1]
        assert len(tip_part) <= 100


# =========================================================================
# 四、元数据测试
# =========================================================================

class TestMetadata:
    """元数据字段完整性与正确性。"""

    def test_child_metadata_fields(self):
        """子块应包含所有必需的元数据字段。"""
        result = build_parent_child_nodes(_make_recipe())
        required_fields = {
            "recipe_id", "title", "category", "tags", "difficulty",
            "difficulty_text", "costtime", "costtime_minutes",
            "ingredient_count", "main_ingredients", "viewnum", "favnum",
            "nutrition_coverage", "nutrition_tags", "nutrition_confidence",
            "has_video", "thumb", "chunk_type",
        }
        for child in result["children"]:
            meta = child["metadata"]
            missing = required_fields - set(meta.keys())
            assert not missing, f"子块缺少字段: {missing}"

    def test_parent_extra_metadata_fields(self):
        """父文档应包含额外的元数据字段。"""
        result = build_parent_child_nodes(_make_recipe())
        parent_meta = result["parent"]["metadata"]
        extra_fields = {
            "videourl", "step_pics", "ingredient_nutrition",
            "nutrition_summary",
        }
        missing = extra_fields - set(parent_meta.keys())
        assert not missing, f"父文档缺少额外字段: {missing}"

    def test_parent_chunk_type(self):
        result = build_parent_child_nodes(_make_recipe())
        assert result["parent"]["metadata"]["chunk_type"] == "parent"

    def test_main_ingredients_excludes_seasoning(self):
        """main_ingredients 应排除调味品。"""
        result = build_parent_child_nodes(_make_recipe())
        meta = result["children"][0]["metadata"]
        assert "花菜" in meta["main_ingredients"]
        assert "五花肉" in meta["main_ingredients"]
        assert "盐" not in meta["main_ingredients"]

    def test_main_ingredients_max_5(self):
        """main_ingredients 最多取前5个。"""
        nutrition = [
            {
                "name": f"食材{i}", "matched_name": f"食材{i}",
                "energy": 100.0, "protein": 10.0, "fat": 5.0, "carbs": 20.0,
                "match_score": 100, "match_type": "exact",
            }
            for i in range(8)
        ]
        recipe = _make_recipe(ingredient_nutrition=nutrition)
        result = build_parent_child_nodes(recipe)
        meta = result["children"][0]["metadata"]
        assert len(meta["main_ingredients"]) == 5

    def test_costtime_minutes(self):
        result = build_parent_child_nodes(_make_recipe())
        meta = result["children"][0]["metadata"]
        assert meta["costtime_minutes"] == 20

    def test_has_video_false(self):
        result = build_parent_child_nodes(_make_recipe(videourl=""))
        meta = result["children"][0]["metadata"]
        assert meta["has_video"] is False

    def test_has_video_true(self):
        result = build_parent_child_nodes(
            _make_recipe(videourl="http://video.mp4")
        )
        meta = result["children"][0]["metadata"]
        assert meta["has_video"] is True

    def test_difficulty_text_mapping(self):
        for level, text in DIFFICULTY_MAP.items():
            result = build_parent_child_nodes(_make_recipe(difficulty=level))
            meta = result["children"][0]["metadata"]
            assert meta["difficulty_text"] == text

    def test_recipe_id_is_string(self):
        result = build_parent_child_nodes(_make_recipe())
        meta = result["children"][0]["metadata"]
        assert isinstance(meta["recipe_id"], str)
        assert meta["recipe_id"] == "1395626"


# =========================================================================
# 五、边界情况测试
# =========================================================================

class TestEdgeCases:
    """边界情况覆盖。"""

    def test_empty_ingredients(self):
        """空食材列表不应报错。"""
        recipe = _make_recipe(
            ingredients_raw=[],
            ingredients_clean=[],
            quantities=[],
            ingredient_count=0,
            ingredient_nutrition=[],
        )
        result = build_parent_child_nodes(recipe)
        assert result["parent"]["text"]  # 不为空
        assert len(result["children"]) == 3

    def test_empty_steps(self):
        """空步骤列表不应报错。"""
        recipe = _make_recipe(steps=[], step_count=0)
        result = build_parent_child_nodes(recipe)
        parent_text = result["parent"]["text"]
        assert "做法步骤" not in parent_text
        step_chunk = result["children"][2]
        assert step_chunk["text"]  # 不为空

    def test_low_confidence_no_nutrition_in_parent(self):
        """low 置信度时父文档不含营养概况。"""
        recipe = _make_recipe(nutrition_confidence="low")
        result = build_parent_child_nodes(recipe)
        assert "营养概况" not in result["parent"]["text"]

    def test_missing_nutrition_summary(self):
        """缺少 nutrition_summary 时不应报错。"""
        recipe = _make_recipe(
            nutrition_summary=None,
            nutrition_confidence="high",
        )
        result = build_parent_child_nodes(recipe)
        # 没有 summary 数据则不显示营养段落
        assert result["parent"]["text"]

    def test_none_ingredient_nutrition(self):
        """ingredient_nutrition 为 None 时不应报错。"""
        recipe = _make_recipe(ingredient_nutrition=None)
        result = build_parent_child_nodes(recipe)
        meta = result["children"][0]["metadata"]
        assert meta["main_ingredients"] == []

    def test_partial_quantities(self):
        """quantities 数量少于 ingredients_raw 时不应报错。"""
        recipe = _make_recipe(
            ingredients_raw=["鸡蛋", "番茄", "盐"],
            quantities=["3个"],
        )
        result = build_parent_child_nodes(recipe)
        text = result["parent"]["text"]
        assert "鸡蛋 3个" in text
        assert "- 番茄" in text
        assert "- 盐" in text


# =========================================================================
# 六、批量构建测试
# =========================================================================

class TestBuildAllNodes:
    """build_all_nodes 批量接口。"""

    def test_returns_list(self):
        recipes = [_make_recipe(), _make_recipe(did="999", title="测试菜")]
        result = build_all_nodes(recipes)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_each_item_has_parent_and_children(self):
        recipes = [_make_recipe()]
        result = build_all_nodes(recipes)
        assert "parent" in result[0]
        assert "children" in result[0]
        assert len(result[0]["children"]) == 3

    def test_empty_input(self):
        assert build_all_nodes([]) == []
