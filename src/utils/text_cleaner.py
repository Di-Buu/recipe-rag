"""
食谱文本清洗工具

对食谱描述、步骤、小贴士等用户生成内容进行规范化处理：
- 繁体转简体
- 去除多余空格和空白字符
- 规范中文标点
- 移除 URL
- 清理步骤序号
- 去除常见口语化填充词
"""

import re

from opencc import OpenCC

# 繁→简转换器（单例）
_t2s = OpenCC("t2s")

# URL 正则
_URL_RE = re.compile(
    r"https?://[^\s，。！？）\)》」】\u3000]+"
)

# 连续空白（含全角空格）→ 单个空格
_MULTI_SPACE_RE = re.compile(r"[\s\u3000]{2,}")

# 步骤文本开头的序号，例如 "1. " "1、" "1，"
_STEP_NUM_RE = re.compile(r"^\d+[\s]*[.、，,．]\s*")

# 半角标点 → 全角标点映射
_PUNCT_MAP = {
    ",": "，",
    ":": "：",
    ";": "；",
    "!": "！",
    "?": "？",
    "(": "（",
    ")": "）",
}

# 需要保留半角的上下文（数字相关，如 "1.5g", "10:30"）
_KEEP_HALF_RE = re.compile(r"\d[,.:;]\d")

# 口语化填充词/短语
_FILLER_PATTERNS = [
    re.compile(r"哈哈哈+"),
    re.compile(r"嘿嘿嘿*"),
    re.compile(r"呵呵呵*"),
    re.compile(r"啦啦啦+"),
    re.compile(r"~+"),
    re.compile(r"\.{4,}"),
    re.compile(r"。{2,}"),
]


def clean_text(text: str) -> str:
    """通用文本清洗：去空白、移除 URL、规范标点"""
    if not text:
        return ""

    # 繁体→简体
    text = _t2s.convert(text)

    # 移除 URL
    text = _URL_RE.sub("", text)

    # 去除口语化填充
    for pattern in _FILLER_PATTERNS:
        text = pattern.sub("", text)

    # 规范标点（保留数字间的半角标点）
    result = []
    i = 0
    while i < len(text):
        if text[i] in _PUNCT_MAP:
            # 检查是否在数字之间
            prev_digit = i > 0 and text[i - 1].isdigit()
            next_digit = i + 1 < len(text) and text[i + 1].isdigit()
            if prev_digit and next_digit:
                result.append(text[i])
            else:
                result.append(_PUNCT_MAP[text[i]])
        else:
            result.append(text[i])
        i += 1
    text = "".join(result)

    # 连续空白 → 单空格
    text = _MULTI_SPACE_RE.sub(" ", text)

    return text.strip()


def clean_description(desc: str) -> str:
    """清洗食谱描述"""
    return clean_text(desc)


def clean_step(step: str) -> str:
    """清洗单个步骤文本：去序号 + 通用清洗"""
    if not step:
        return ""
    text = _STEP_NUM_RE.sub("", step)
    return clean_text(text)


def clean_tip(tip: str) -> str:
    """清洗小贴士：统一分隔编号格式 + 通用清洗"""
    if not tip:
        return ""
    text = clean_text(tip)
    # 统一 "1，" "1." 等为 "1、"
    text = re.sub(r"(?<!\d)(\d+)\s*[.，,．]\s*(?=\S)", r"\1、", text)
    return text


def clean_recipe_detail(detail: dict) -> dict:
    """清洗食谱详情的所有文本字段（原地修改并返回）"""
    if "desc" in detail:
        detail["desc"] = clean_description(detail["desc"])

    if "tip" in detail:
        detail["tip"] = clean_tip(detail["tip"])

    if "steps" in detail and isinstance(detail["steps"], list):
        detail["steps"] = [clean_step(s) for s in detail["steps"]]

    if "title" in detail:
        detail["title"] = clean_text(detail["title"])

    return detail
