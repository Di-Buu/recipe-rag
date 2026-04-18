"""
CSV 数据加载器

职责：读取豆果美食 CSV 原始数据，解析 # 分隔字段，返回结构化食谱字典列表。
不做任何清洗或过滤，仅做格式解析。
"""

import csv
from pathlib import Path
from typing import Any


def parse_hash_field(value: str) -> list[str]:
    """
    解析 # 分隔的字段值。

    规则：
    - 先去除末尾的 # 分隔符
    - 按 # 拆分
    - 对每一项做 strip()
    - 保留空项（用于保持 yl/fl 的位置对齐）
    """
    if not value or not value.strip():
        return []
    items = value.rstrip("#").split("#")
    return [item.strip() for item in items]


def parse_hash_field_nonempty(value: str) -> list[str]:
    """解析 # 分隔字段，过滤掉空项（用于 steptext 等不需要位置对齐的字段）"""
    if not value or not value.strip():
        return []
    items = value.rstrip("#").split("#")
    return [item.strip() for item in items if item.strip()]


def load_csv(csv_path: str | Path) -> list[dict[str, Any]]:
    """
    读取原始 CSV 文件，返回食谱字典列表。

    每条记录保持原始字段值，仅做基础类型转换：
    - difficulty: str → int
    - viewnum/favnum: str → int
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {csv_path}")

    records = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {
                "did": row["did"].strip(),
                "title": row["title"].strip(),
                "zid": row["zid"].strip(),
                "cid": row.get("cid", ""),
                "desc": row.get("desc", "").strip(),
                "difficulty": _safe_int(row.get("difficulty", "0")),
                "costtime": row.get("costtime", "").strip(),
                "tip": row.get("tip", "").strip(),
                "yl": row.get("yl", ""),
                "fl": row.get("fl", ""),
                "steptext": row.get("steptext", ""),
                "thumb": row.get("thumb", "").strip(),
                "videourl": row.get("videourl", "").strip(),
                "steppic": row.get("steppic", ""),
                "viewnum": _safe_int(row.get("viewnum", "0")),
                "favnum": _safe_int(row.get("favnum", "0")),
            }
            records.append(record)

    return records


def _safe_int(value: str, default: int = 0) -> int:
    """安全的字符串转整数"""
    try:
        return int(value.strip()) if value and value.strip() else default
    except ValueError:
        return default
