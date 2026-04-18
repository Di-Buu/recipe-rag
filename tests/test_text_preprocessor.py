"""食谱文本预清洗模块测试"""

import pytest
from src.data.text_preprocessor import clean_text, preprocess_recipe, preprocess_all


# ============================================================
# 1. 白名单测试
# ============================================================
class TestWhitelist:
    """白名单过滤测试"""

    def test_preserve_chinese_and_punctuation(self):
        """保留中文和常用标点"""
        text = "花菜切成小朵，加盐腌制。"
        assert clean_text(text) == text

    def test_preserve_unit_symbols(self):
        """保留温度等单位符号"""
        text = "烤箱预热180℃"
        assert clean_text(text) == text

    def test_remove_emoji(self):
        """移除 emoji"""
        assert clean_text("好好吃❤️") == "好好吃"

    def test_remove_emoticon(self):
        """移除颜文字"""
        assert clean_text("╮(╯▽╰)╭") == ""

    def test_remove_decorative_symbols(self):
        """移除装饰符"""
        assert clean_text("★☆★") == ""

    def test_preserve_numbers_and_english(self):
        """保留数字和英文"""
        text = "加入200ml水和salt"
        assert clean_text(text) == text

    def test_preserve_step_numbers(self):
        """保留步骤编号"""
        text = "1. 将鸡蛋打散"
        assert clean_text(text) == text

    def test_preserve_fractions(self):
        """保留分数符号"""
        text = "加入½杯面粉"
        assert clean_text(text) == text

    def test_preserve_math_symbols(self):
        """保留数学符号"""
        text = "温度≤200℃"
        assert clean_text(text) == text

    def test_preserve_slash(self):
        """保留斜杠"""
        text = "糖/盐比例1:2"
        assert clean_text(text) == text

    def test_preserve_chinese_quotes(self):
        """保留中文引号"""
        text = "\u201c红烧肉\u201d是经典菜"
        assert clean_text(text) == text

    def test_preserve_fullwidth_tilde(self):
        """保留全角波浪号"""
        text = "大约～100克"
        assert clean_text(text) == text


# ============================================================
# 2. 广告清除测试
# ============================================================
class TestAdRemoval:
    """广告/推广信息移除测试"""

    def test_remove_wechat_ad(self):
        """移除微信广告"""
        assert clean_text("加我微信xxx获取更多食谱") == ""

    def test_remove_wechat_number(self):
        """移除微信号"""
        assert clean_text("微信号：xiaochufang123") == ""

    def test_remove_public_account(self):
        """移除公众号推广"""
        assert clean_text("关注公众号：美食天地") == ""

    def test_remove_weibo_ad(self):
        """移除微博推广"""
        assert clean_text("微博：美食达人小王") == ""

    def test_remove_vx_ad(self):
        """移除V信推广"""
        assert clean_text("V信：food123") == ""

    def test_preserve_wechat_pay(self):
        """微信支付不应被误删"""
        text = "可以用微信支付购买食材"
        assert clean_text(text) == text

    def test_preserve_wechat_hongbao(self):
        """微信红包不应被误删"""
        text = "收到微信红包买了食材"
        assert clean_text(text) == text

    def test_multiline_ad_removal(self):
        """多行文本中仅移除广告行"""
        text = "这道菜很好吃\n加我微信xxx获取更多\n记得收藏哦"
        assert clean_text(text) == "这道菜很好吃\n记得收藏哦"

    def test_remove_follow_me(self):
        """移除关注我"""
        assert clean_text("好吃就关注我吧") == ""

    def test_remove_dm_me(self):
        """移除私信我"""
        assert clean_text("有问题私信我哦") == ""


# ============================================================
# 3. 连续装饰符测试
# ============================================================
class TestRepeatedPunctuation:
    """连续装饰符简化测试"""

    def test_simplify_repeated_tilde_fullwidth(self):
        """全角波浪号简化：4个 → 2个"""
        assert clean_text("好吃～～～～") == "好吃～～"

    def test_simplify_repeated_exclamation(self):
        """感叹号简化：4个 → 2个"""
        assert clean_text("太好了！！！！") == "太好了！！"

    def test_simplify_repeated_period(self):
        """句号简化：4个 → 2个"""
        assert clean_text("嗯。。。。") == "嗯。。"

    def test_simplify_repeated_tilde_halfwidth(self):
        """半角波浪号简化：3个 → 1个"""
        assert clean_text("好吃~~~") == "好吃~"

    def test_keep_two_punctuation(self):
        """保留2个相同标点（不触发简化）"""
        assert clean_text("好吃～～") == "好吃～～"
        assert clean_text("太好了！！") == "太好了！！"

    def test_simplify_exactly_three(self):
        """恰好3个标点 → 2个"""
        assert clean_text("好吃！！！") == "好吃！！"


# ============================================================
# 4. 食谱级测试
# ============================================================
class TestPreprocessRecipe:
    """食谱级测试"""

    def test_clean_all_text_fields(self):
        """验证 desc、tip、steps 都被清洗"""
        recipe = {
            "name": "红烧肉",
            "desc": "超好吃❤️",
            "tip": "记得小火慢炖★",
            "steps": ["1. 切块❤️", "2. 焯水★☆"],
            "ingredients": ["五花肉", "酱油"],
        }
        result = preprocess_recipe(recipe)
        assert result["desc"] == "超好吃"
        assert result["tip"] == "记得小火慢炖"
        assert result["steps"] == ["1. 切块", "2. 焯水"]

    def test_preserve_other_fields(self):
        """验证其他字段不受影响"""
        recipe = {
            "name": "红烧肉❤️",
            "desc": "简单好吃",
            "ingredients": ["五花肉", "酱油"],
            "cuisine": "川菜",
        }
        result = preprocess_recipe(recipe)
        assert result["name"] == "红烧肉❤️"  # name 不被清洗
        assert result["ingredients"] == ["五花肉", "酱油"]
        assert result["cuisine"] == "川菜"

    def test_handle_missing_fields(self):
        """处理缺失字段"""
        recipe = {"name": "红烧肉"}
        result = preprocess_recipe(recipe)
        assert result == {"name": "红烧肉"}

    def test_handle_none_desc(self):
        """处理 None 值的 desc"""
        recipe = {"name": "红烧肉", "desc": None}
        result = preprocess_recipe(recipe)
        assert result["desc"] == ""

    def test_steps_list_elements_cleaned(self):
        """验证 steps 列表中每个元素都被清洗"""
        recipe = {
            "steps": [
                "1. 准备食材❤️",
                "2. 开始烹饪★☆★",
                "3. 出锅～～～～",
            ]
        }
        result = preprocess_recipe(recipe)
        assert result["steps"] == [
            "1. 准备食材",
            "2. 开始烹饪",
            "3. 出锅～～",
        ]

    def test_original_not_modified(self):
        """验证原始字典不被修改"""
        recipe = {"desc": "好吃❤️", "steps": ["1. 做法★"]}
        original_desc = recipe["desc"]
        original_steps = recipe["steps"][:]
        preprocess_recipe(recipe)
        assert recipe["desc"] == original_desc
        assert recipe["steps"] == original_steps


# ============================================================
# 5. 批量预清洗测试
# ============================================================
class TestPreprocessAll:
    """批量预清洗测试"""

    def test_batch_preprocess(self):
        """批量清洗多个食谱"""
        recipes = [
            {"desc": "好吃❤️", "steps": ["1. 做法"]},
            {"desc": "简单★", "tip": "注意火候"},
        ]
        results = preprocess_all(recipes)
        assert len(results) == 2
        assert results[0]["desc"] == "好吃"
        assert results[1]["desc"] == "简单"

    def test_empty_list(self):
        """空列表"""
        assert preprocess_all([]) == []


# ============================================================
# 6. 边界情况测试
# ============================================================
class TestEdgeCases:
    """边界情况测试"""

    def test_empty_string(self):
        """空字符串"""
        assert clean_text("") == ""

    def test_none_value(self):
        """None 值"""
        assert clean_text(None) == ""

    def test_pure_emoji(self):
        """纯 emoji 字符串"""
        assert clean_text("❤️🔥💕") == ""

    def test_whitespace_only(self):
        """纯空白字符串"""
        assert clean_text("   \n\n  ") == ""

    def test_mixed_content(self):
        """混合内容综合测试"""
        text = "这道菜很好吃❤️！！！太棒了★\n加我微信abc获取更多\n烤箱预热180℃"
        result = clean_text(text)
        assert "好吃" in result
        assert "❤" not in result
        assert "★" not in result
        assert "微信" not in result
        assert "180℃" in result
        assert "！！" in result  # 3个！→ 2个
