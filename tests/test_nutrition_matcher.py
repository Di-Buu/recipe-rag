"""NutritionMatcher 单元测试"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from src.data.nutrition_matcher import NutritionMatcher


DB_PATH = Path(__file__).parent.parent / "data" / "processed" / "food_nutrition.db"


@pytest.fixture
def matcher():
    """创建匹配器实例（mock 数据库加载）"""
    with patch.object(NutritionMatcher, '_load_database'):
        matcher_obj = NutritionMatcher(Path("dummy.db"))
    return matcher_obj


@pytest.fixture
def real_matcher():
    """创建使用真实数据库的匹配器实例"""
    return NutritionMatcher(DB_PATH)


class TestParseValue:
    """测试 _parse_value 解析带单位营养值"""

    def test_parse_kj(self, matcher):
        assert matcher._parse_value("1698kJ") == 1698.0

    def test_parse_g(self, matcher):
        assert matcher._parse_value("0.1g") == 0.1

    def test_parse_mg(self, matcher):
        assert matcher._parse_value("5.40mg") == 5.4

    def test_parse_ug(self, matcher):
        assert matcher._parse_value("12.5μg") == 12.5

    def test_parse_dash(self, matcher):
        """'—' 表示未测定"""
        assert matcher._parse_value("—") == 0.0

    def test_parse_tr(self, matcher):
        """'Tr' 表示未检出（微量）"""
        assert matcher._parse_value("Tr") == 0.0

    def test_parse_empty(self, matcher):
        """空字符串"""
        assert matcher._parse_value("") == 0.0

    def test_parse_none(self, matcher):
        """None 值"""
        assert matcher._parse_value(None) == 0.0

    def test_parse_integer(self, matcher):
        """纯整数带单位"""
        assert matcher._parse_value("100g") == 100.0

    def test_parse_whitespace(self, matcher):
        """带空白"""
        assert matcher._parse_value("  1698kJ  ") == 1698.0


class TestLoadDatabase:
    """测试数据库加载"""

    def test_food_map_not_empty(self, real_matcher):
        """应加载 1346 条食物"""
        assert len(real_matcher._food_map) > 1000

    def test_food_map_has_known_food(self, real_matcher):
        """已知食物应存在"""
        assert '精盐' in real_matcher._food_map
        assert '糖（白砂糖）' in real_matcher._food_map
        assert '大蒜[蒜头](鲜)' in real_matcher._food_map

    def test_energy_is_kcal(self, real_matcher):
        """能量应已转换为 kcal（原始为 kJ）"""
        salt = real_matcher._food_map['精盐']
        assert salt[2] == 0.0
        
        sugar = real_matcher._food_map['糖（白砂糖）']
        assert 400 < sugar[2] < 410

    def test_protein_parsed(self, real_matcher):
        """蛋白质应已去单位"""
        egg = real_matcher._food_map['蛋（鸡蛋，均值)']
        assert 10 < egg[3] < 20

    def test_alias_from_brackets(self, real_matcher):
        """应从 [] 中提取别名"""
        assert '蒜头' in real_matcher._alias_to_main
        assert real_matcher._alias_to_main['蒜头'] == '大蒜[蒜头](鲜)'

    def test_pure_name_alias(self, real_matcher):
        """去掉括号后的纯名也应作为别名"""
        assert '大蒜' in real_matcher._alias_to_main

    def test_food_names_list(self, real_matcher):
        """_food_names 列表应与 _food_map 同步"""
        assert len(real_matcher._food_names) == len(real_matcher._food_map)


from src.data.nutrition_matcher import COMMON_SEASONINGS


class TestCommonSeasonings:
    """测试 COMMON_SEASONINGS 精简后的正确性"""

    def test_water_variants(self):
        """水的各种说法都应在内"""
        for name in ['水', '清水', '凉水', '冷水', '温水', '开水', '热水']:
            assert name in COMMON_SEASONINGS, f"缺少: {name}"
            assert COMMON_SEASONINGS[name] == (0, 0, 0, 0)

    def test_packaging_materials(self):
        """包装材料应在内"""
        for name in ['锡纸', '油纸', '保鲜膜', '牙签', '竹签']:
            assert name in COMMON_SEASONINGS, f"缺少: {name}"

    def test_real_seasonings_removed(self):
        """有营养价值的调味料不应在 COMMON_SEASONINGS 中"""
        should_not_be_here = [
            '盐', '糖', '酱油', '生抽', '老抽', '醋', '料酒',
            '味精', '鸡精', '花椒', '胡椒粉', '五香粉',
        ]
        for name in should_not_be_here:
            assert name not in COMMON_SEASONINGS, f"不应包含: {name}"

    def test_count(self):
        """总数应约 100-200 条"""
        assert 100 <= len(COMMON_SEASONINGS) <= 200


from src.data.nutrition_matcher import ALIAS_MAP


class TestAliasMap:
    """测试 ALIAS_MAP 目标名称与数据库一致性"""

    def test_all_targets_exist_in_db(self, real_matcher):
        """ALIAS_MAP 的每个目标值都必须存在于数据库中"""
        missing = []
        for alias, target in ALIAS_MAP.items():
            if target not in real_matcher._food_map:
                missing.append(f"  {alias} → {target}")
        if missing:
            pytest.fail(
                f"ALIAS_MAP 中 {len(missing)} 个目标不在数据库中:\n"
                + "\n".join(missing[:20])
            )

    def test_no_duplicate_aliases(self):
        """不应有重复的别名键"""
        keys = list(ALIAS_MAP.keys())
        assert len(keys) == len(set(keys))

    def test_core_mappings(self, real_matcher):
        """核心高频食材映射正确"""
        core = {
            '鸡蛋': '蛋（鸡蛋，均值)',
            '五花肉': '猪肉(肋条肉)',
            '面粉': '小麦粉(标准粉)',
            '土豆': '马铃薯[土豆，洋芋]',
            '西红柿': '番茄[西红柿]',
            '生抽': '生抽',
            '盐': '精盐',
            '糖': '糖（白砂糖）',
            '牛奶': '乳品（牛乳，均值)',
        }
        for alias, expected_target in core.items():
            assert alias in ALIAS_MAP, f"缺少核心映射: {alias}"
            assert ALIAS_MAP[alias] == expected_target, (
                f"{alias}: 期望 '{expected_target}'，实际 '{ALIAS_MAP[alias]}'"
            )
            assert expected_target in real_matcher._food_map, (
                f"目标 '{expected_target}' 不在数据库中"
            )


class TestNormalizeName:
    """测试名称规范化"""

    def test_plain_name(self, matcher):
        assert matcher._normalize_name('鸡蛋') == '鸡蛋'

    def test_strip_prefix(self, matcher):
        """去除修饰前缀"""
        assert matcher._normalize_name('新鲜鸡蛋') == '鸡蛋'
        assert matcher._normalize_name('有机牛奶') == '牛奶'

    def test_strip_parentheses(self, matcher):
        """去除括号内容"""
        assert matcher._normalize_name('五花肉（去皮）') == '五花肉'
        assert matcher._normalize_name('五花肉(去皮)') == '五花肉'

    def test_protected_names(self, matcher):
        """保护名称不被修改"""
        assert matcher._normalize_name('生抽') == '生抽'
        assert matcher._normalize_name('老抽') == '老抽'
        assert matcher._normalize_name('干辣椒') == '干辣椒'

    def test_normalize_brackets(self, matcher):
        """全角括号应统一为半角处理"""
        assert matcher._normalize_name('牛肉（切丁）') == '牛肉'
        assert matcher._normalize_name('牛肉(切丁)') == '牛肉'

    def test_empty_string(self, matcher):
        assert matcher._normalize_name('') == ''


class TestIntegration:
    """集成冒烟测试"""

    def test_match_from_common_seasonings(self, real_matcher):
        """COMMON_SEASONINGS 匹配"""
        result = real_matcher.match('水')
        assert result is not None
        assert result.id == -1
        assert result.energy == 0

    def test_match_from_alias_map(self, real_matcher):
        """ALIAS_MAP 匹配"""
        result = real_matcher.match('五花肉')
        assert result is not None
        assert result.match_score == 100
        assert result.name == '猪肉(肋条肉)'
        assert result.energy > 0

    def test_match_db_direct(self, real_matcher):
        """数据库直接匹配"""
        result = real_matcher.match('精盐')
        assert result is not None
        assert result.match_score == 100

    def test_match_db_alias_bracket(self, real_matcher):
        """数据库别名匹配（从[]提取）"""
        result = real_matcher.match('蒜头')
        assert result is not None
        assert '大蒜' in result.name

    def test_match_fuzzy(self, real_matcher):
        """模糊匹配"""
        result = real_matcher.match('西红柿酱')
        if result:
            assert result.match_score < 100

    def test_unmatched(self, real_matcher):
        """不存在的食材应返回 None"""
        result = real_matcher.match('完全不存在的食材ABC')
        assert result is None

    def test_energy_is_kcal_not_kj(self, real_matcher):
        """能量应为 kcal 不是 kJ"""
        result = real_matcher.match('糖')
        assert result is not None
        assert result.energy < 500

    def test_batch_match(self, real_matcher):
        """批量匹配"""
        results = real_matcher.batch_match(['鸡蛋', '盐', '水', '不存在'])
        assert len(results) == 4
        assert results['鸡蛋'] is not None
        assert results['不存在'] is None


from src.data.nutrition_matcher import MANUAL_NUTRITION, MANUAL_ALIASES, COMBO_SPLITS


class TestManualNutrition:
    """测试手工补充营养数据"""

    def test_manual_direct_match(self, real_matcher):
        """手工营养数据直接匹配"""
        result = real_matcher.match('八角')
        assert result is not None
        assert result.id == -3
        assert result.energy == 281
        assert result.match_score == 100

    def test_manual_alias_match(self, real_matcher):
        """手工别名映射匹配"""
        result = real_matcher.match('大料')
        assert result is not None
        assert result.energy == 281  # 与八角相同
        assert result.match_score == 100

    def test_manual_oyster_sauce(self, real_matcher):
        """蚝油（含错别字映射"耗油"）"""
        r1 = real_matcher.match('蚝油')
        r2 = real_matcher.match('耗油')
        assert r1 is not None and r2 is not None
        assert r1.energy == r2.energy == 80

    def test_all_manual_entries_reachable(self, real_matcher):
        """所有 MANUAL_NUTRITION 条目均可匹配"""
        for name in MANUAL_NUTRITION:
            result = real_matcher.match(name)
            assert result is not None, f"无法匹配手工条目: {name}"

    def test_all_manual_aliases_reachable(self, real_matcher):
        """所有 MANUAL_ALIASES 别名均可匹配"""
        for alias, target in MANUAL_ALIASES.items():
            result = real_matcher.match(alias)
            assert result is not None, f"无法匹配手工别名: {alias} → {target}"


class TestComboSplits:
    """测试组合词拆分"""

    def test_cong_jiang_suan(self, real_matcher):
        """葱姜蒜应拆分为三种食材取平均"""
        result = real_matcher.match('葱姜蒜')
        assert result is not None
        assert result.id == -2
        assert '+' in result.name
        assert result.energy > 0
        assert result.match_score == 100

    def test_cong_jiang(self, real_matcher):
        """葱姜拆分"""
        result = real_matcher.match('葱姜')
        assert result is not None
        assert result.id == -2

    def test_combo_not_in_common_seasonings(self):
        """组合词不应在 COMMON_SEASONINGS 中"""
        for combo in COMBO_SPLITS:
            assert combo not in COMMON_SEASONINGS, f"{combo} 不应在零营养列表中"


class TestUserCorrections:
    """测试用户审核后的修正"""

    def test_cong_maps_to_xiaocong(self, real_matcher):
        """葱应匹配到小葱而非大葱"""
        result = real_matcher.match('葱')
        assert result is not None
        assert '小葱' in result.name

    def test_qingjiao_maps_to_lajiao(self, real_matcher):
        """青椒应匹配到辣椒(青,尖)"""
        result = real_matcher.match('青椒')
        assert result is not None
        assert '辣椒' in result.name

    def test_baijiu_not_wine(self, real_matcher):
        """白酒不应匹配到白葡萄酒"""
        result = real_matcher.match('白酒')
        assert result is not None
        assert '葡萄酒' not in result.name

    def test_jiu_maps_to_liaojiu(self, real_matcher):
        """酒应匹配到料酒"""
        result = real_matcher.match('酒')
        assert result is not None
        assert '料酒' in result.name

    def test_rou_maps_to_pork(self, real_matcher):
        """肉应匹配到猪肉"""
        result = real_matcher.match('肉')
        assert result is not None
        assert '猪肉' in result.name

    def test_guipi_zero_nutrition(self, real_matcher):
        """桂皮应为零营养"""
        result = real_matcher.match('桂皮')
        assert result is not None
        assert result.energy == 0


class TestSuffixStripping:
    """测试后缀剥离回退"""

    def test_huluobo_si(self, real_matcher):
        """胡萝卜丝→胡萝卜"""
        result = real_matcher.match('胡萝卜丝')
        assert result is not None
        assert '胡萝卜' in result.name
        assert result.match_score == 90

    def test_short_name_no_strip(self, real_matcher):
        """2字名称不触发后缀剥离（防止粉丝→粉误匹配）"""
        result = real_matcher.match('粉丝')
        assert result is not None
        assert result.match_score == 100  # 应通过 ALIAS_MAP 直接匹配
