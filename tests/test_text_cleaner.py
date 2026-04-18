"""text_cleaner 单元测试"""

import pytest

from src.utils.text_cleaner import (
    clean_text,
    clean_description,
    clean_step,
    clean_tip,
    clean_recipe_detail,
)


class TestCleanText:
    """通用清洗函数"""

    def test_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_multi_spaces(self):
        assert clean_text("妈妈 牌  午餐肉") == "妈妈 牌 午餐肉"

    def test_remove_url(self):
        text = "欢迎到我的博客玩 -- http://blog.sina.com.cn/s/blog_123.html"
        result = clean_text(text)
        assert "http" not in result
        assert "欢迎到我的博客玩" in result

    def test_normalize_punctuation(self):
        assert "，" in clean_text("加入盐,糖")
        assert "：" in clean_text("准备材料:")

    def test_keep_numeric_punctuation(self):
        result = clean_text("需要1.5克盐")
        assert "1.5" in result

    def test_remove_fillers(self):
        assert "哈哈哈" not in clean_text("太好吃了哈哈哈")
        result = clean_text("做好了~~~")
        assert "~" not in result

    def test_fullwidth_space(self):
        result = clean_text("准备\u3000\u3000食材")
        assert "\u3000" not in result


class TestCleanStep:
    """步骤清洗"""

    def test_remove_numbering(self):
        assert clean_step("1. 菜花掰成小花") == "菜花掰成小花"
        assert clean_step("2、加入调料") == "加入调料"
        assert clean_step("3，放入锅中") == "放入锅中"

    def test_no_number(self):
        assert clean_step("菜花掰成小花") == "菜花掰成小花"

    def test_empty(self):
        assert clean_step("") == ""


class TestCleanTip:
    """小贴士清洗"""

    def test_unify_numbering(self):
        result = clean_tip("1.先加盐 2.再加糖")
        assert "1、" in result
        assert "2、" in result

    def test_remove_url_in_tip(self):
        tip = "详情请看 https://example.com/recipe 了解更多"
        assert "https" not in clean_tip(tip)


class TestCleanRecipeDetail:
    """整合清洗"""

    def test_cleans_all_fields(self):
        detail = {
            "title": "妈妈 牌午餐肉",
            "desc": "很好吃~~~  试试吧",
            "steps": ["1. 切肉", "2. 搅拌"],
            "tip": "1.注意火候 2.别忘加盐",
        }
        result = clean_recipe_detail(detail)
        assert "~" not in result["desc"]
        assert not result["steps"][0].startswith("1")
        assert "1、" in result["tip"]

    def test_missing_fields(self):
        detail = {"title": "简单菜"}
        result = clean_recipe_detail(detail)
        assert result["title"] == "简单菜"

    def test_traditional_to_simplified(self):
        assert clean_text("紅燒獅子頭") == "红烧狮子头"
        assert clean_text("雞蛋與麵粉攪拌均勻") == "鸡蛋与面粉搅拌均匀"
        detail = {"title": "糖醋魚", "desc": "這道菜很好吃"}
        result = clean_recipe_detail(detail)
        assert result["title"] == "糖醋鱼"
        assert result["desc"] == "这道菜很好吃"
