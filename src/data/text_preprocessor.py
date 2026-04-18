"""
食谱文本预清洗模块

在文档构建前对食谱的文本字段进行清洗：
- 白名单过滤：仅保留中文、英文、数字、常用标点和特殊符号
- 广告/推广信息移除：删除包含微信号、公众号等推广信息的文本行
- 连续装饰符简化：规范化重复标点
- 不改变文本语义，不清理口语化表达，不修改步骤编号
"""

import re


# ============================================================
# 白名单正则：不在此范围内的字符将被移除
# ============================================================
_WHITELIST_PATTERN = re.compile(
    '[^'
    '\u4e00-\u9fff'                                          # 中文字符
    '，。！？；：、\u201c\u201d\u2018\u2019（）【】《》…—'    # 中文标点
    'a-zA-Z0-9'                                               # 英文字母和数字
    '.,:;!?\'\"()\\[\\]'                                      # 常用英文标点
    '\\s'                                                      # 空格和换行
    '℃°㎜㎝㎏㎎㎡％‰⅓⅔¼½¾'                                   # 特殊单位符号
    '×÷±≈≤≥＋＝'                                               # 数学符号
    '/～~'                                                     # 斜杠和波浪号
    '\\-'                                                      # 连字符
    ']'
)

# ============================================================
# 广告/推广模式
# ============================================================
# 匹配到这些模式的整行将被移除
_AD_LINE_PATTERNS = [
    re.compile(r'微信[号：:]'),
    re.compile(r'加我?微信(?!支付|红包)'),
    re.compile(r'公众号[：:]'),
    re.compile(r'V[信xX][：:]'),
    re.compile(r'微博[：:]'),
]

# 仅在行末尾出现时移除整行
_AD_TAIL_PATTERNS = [
    re.compile(r'关注我.{0,30}$'),
    re.compile(r'私信我.{0,30}$'),
]

# ============================================================
# 连续标点简化
# ============================================================
# 通用规则：3个以上相同标点 → 保留2个
_REPEATED_PUNCT_PATTERN = re.compile(
    r'([，。！？；：、…—～.,:;!?\'\"＋＝])\1{2,}'
)
# 特殊规则：3个以上半角波浪号 → 保留1个
_REPEATED_TILDE_PATTERN = re.compile(r'~{3,}')

# 空括号对清理（颜文字经白名单过滤后的残留）
_EMPTY_BRACKET_PATTERNS = [
    re.compile(r'\(\s*\)'),
    re.compile(r'\[\s*\]'),
    re.compile(r'（\s*）'),
    re.compile(r'【\s*】'),
    re.compile(r'《\s*》'),
]


def _remove_ads(text: str) -> str:
    """移除包含广告/推广信息的行"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # 检查行内广告模式（微信号、公众号等）
        if any(p.search(stripped) for p in _AD_LINE_PATTERNS):
            continue
        # 检查末尾广告模式（关注我、私信我）
        if any(p.search(stripped) for p in _AD_TAIL_PATTERNS):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def _apply_whitelist(text: str) -> str:
    """白名单过滤，移除不在白名单中的字符"""
    return _WHITELIST_PATTERN.sub('', text)


def _clean_empty_brackets(text: str) -> str:
    """清理空括号对（颜文字经白名单过滤后可能留下空括号）"""
    for p in _EMPTY_BRACKET_PATTERNS:
        text = p.sub('', text)
    return text


def _simplify_repeated_punctuation(text: str) -> str:
    """简化连续重复标点"""
    # 通用规则：3个以上相同标点 → 保留2个
    text = _REPEATED_PUNCT_PATTERN.sub(r'\1\1', text)
    # 特殊规则：3个以上半角波浪号 → 保留1个
    text = _REPEATED_TILDE_PATTERN.sub('~', text)
    return text


def _normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    # 多个空格/制表符 → 单个空格
    text = re.sub(r'[ \t]+', ' ', text)
    # 连续3个以上换行 → 2个换行（保留一个空行）
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_text(text: str) -> str:
    """对单个文本字段进行预清洗

    清洗步骤：
    1. 移除广告/推广信息（整行移除）
    2. 白名单字符过滤（移除 emoji、颜文字、装饰符等）
    3. 清理空括号残留
    4. 简化连续重复标点
    5. 规范化空白字符

    Args:
        text: 待清洗的文本，可为 None

    Returns:
        清洗后的文本
    """
    if not text:
        return ""

    # 1. 移除广告/推广信息
    text = _remove_ads(text)
    # 2. 白名单字符过滤
    text = _apply_whitelist(text)
    # 3. 清理空括号残留（颜文字被过滤后可能留下空括号）
    text = _clean_empty_brackets(text)
    # 4. 简化连续重复标点
    text = _simplify_repeated_punctuation(text)
    # 5. 规范化空白字符并去除首尾空白
    text = _normalize_whitespace(text)

    return text


def preprocess_recipe(recipe: dict) -> dict:
    """对食谱的 desc、tip、steps 字段进行预清洗，返回新字典

    仅清洗 desc、tip、steps 三个字段，其他字段原样保留。
    steps 是列表，会对每个元素逐一清洗。

    Args:
        recipe: 原始食谱字典

    Returns:
        清洗后的新食谱字典
    """
    result = recipe.copy()

    # 清洗字符串字段：desc、tip
    for field in ('desc', 'tip'):
        if field in result:
            value = result[field]
            if isinstance(value, str):
                result[field] = clean_text(value)
            elif value is None:
                result[field] = ""

    # 清洗步骤列表
    if 'steps' in result and isinstance(result['steps'], list):
        result['steps'] = [
            clean_text(step) if isinstance(step, str) else step
            for step in result['steps']
        ]

    return result


def preprocess_all(recipes: list[dict]) -> list[dict]:
    """批量预清洗

    Args:
        recipes: 食谱字典列表

    Returns:
        清洗后的食谱字典列表
    """
    return [preprocess_recipe(r) for r in recipes]
