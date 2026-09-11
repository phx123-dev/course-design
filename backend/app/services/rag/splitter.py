# -*- coding: utf-8 -*-
"""
语料切分 —— 按标题/段落切分为检索块（chunk）
============================================
策略（针对中文 Markdown 语料）：
  1) 按行扫描，标题行(#/##/###)作为新块起点，块内累积正文段落；
  2) 单块长度控制在 200~400 字：超长段落按句号/分号断句续切；
  3) 记录每块在原文档中的字符起止位置（char_start/char_end），
     用于前端"依据溯源"精确定位与引用展示。
"""
import re

MIN_CHUNK = 120      # 块最小长度（低于则并入下一块）
MAX_CHUNK = 400      # 块最大长度（超过则断句续切）

HEADING_RE = re.compile(r"^#{1,4}\s+")
SENT_SPLIT_RE = re.compile(r"[。；;!！?？\n]")


def split_markdown(text: str) -> list:
    """切分返回 [{text, char_start, char_end, heading}]"""
    chunks, current, cur_start, cur_heading = [], "", None, ""
    lines = text.split("\n")

    for line in lines:
        if HEADING_RE.match(line):
            # 新标题：收尾当前块
            if current:
                chunks.extend(_flush(current, cur_start, cur_heading))
            cur_heading = line.strip("# ").strip()
            current, cur_start = "", None
            continue
        line = line.strip()
        if not line:
            continue
        start = text.find(line, cur_start + len(current) if cur_start is not None else 0)
        if start < 0:
            start = cur_start + len(current) if cur_start is not None else 0
        if cur_start is None:
            cur_start = start
        current += line

    if current:
        chunks.extend(_flush(current, cur_start, cur_heading))
    return [c for c in chunks if len(c["text"]) >= 30]


def _flush(current: str, cur_start: int, heading: str) -> list:
    """把累积文本按 MAX_CHUNK 断句切分为若干块"""
    result = []
    while len(current) > MAX_CHUNK:
        cut = MAX_CHUNK
        m = SENT_SPLIT_RE.search(current, MIN_CHUNK, MAX_CHUNK + 40)
        if m:
            cut = m.end()
        piece = current[:cut]
        result.append({"text": piece, "char_start": cur_start,
                       "char_end": cur_start + cut, "heading": heading})
        current = current[cut:]
        cur_start += cut
    if current:
        result.append({"text": current, "char_start": cur_start,
                       "char_end": cur_start + len(current), "heading": heading})
    return result
