"""Shared quality text matching helpers.

Legacy conversion and quality gates both need the same engineering vocabulary so
that a link created by an adapter is judged by the same language rules during
audit.
"""

from __future__ import annotations

import re


QUALITY_KEYWORD_GROUPS = {
    "pressure": ["压力", "压入", "mpa", "bar"],
    "position": ["位置", "距离", "高度", "开始位", "结束位", "对焦", "mm", "卡板"],
    "grease": ["油脂", "牌号", "型号", "m21", "epk"],
    "oil_amount": ["注油量", "涂油量", "油量", "注油", "涂油", "g"],
    "torque": ["力矩", "扭矩", "扭力", "nm"],
    "appearance": ["外观", "损伤", "开裂", "锈蚀", "标识", "标签", "漏装", "错装"],
    "poka_yoke": ["防错", "有无检测", "正反", "自动监控", "设备监控"],
    "restricted_substance": ["禁用物质", "elv", "gb/t", "30512", "第三方"],
    "fifo_material": ["先进先出", "fifo", "批次", "投放", "入库", "物料", "零件识别"],
    "marking": ["打标", "标记", "生产日期", "追溯"],
    "riveting": ["铆接", "铆钉", "销轴", "壳体", "支架"],
}


def quality_tokens(*values: str) -> set[str]:
    text = " ".join(value for value in values if value).lower()
    tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{1,4}", text))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
    tokens.update(
        chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))
    )
    for canonical, aliases in QUALITY_KEYWORD_GROUPS.items():
        if any(alias.lower() in text for alias in aliases):
            tokens.add(canonical)
    return {token for token in tokens if token}


def overlap_score(left: set[str], right: set[str]) -> int:
    if not left or not right:
        return 0
    return len(left & right)
