# -*- coding: utf-8 -*-
"""
文本向量化 —— 特征哈希 + TF 权重（确定性、零外部依赖）
======================================================
设计选择：不依赖外部 Embedding 模型（课设环境离线可用、结果可复现），
采用经典的 VSM（向量空间模型）变体：
  1) jieba 中文分词，过滤停用词与单字；
  2) 特征哈希（hashing trick）：token → murmur/内置 hash → [0, DIM) 桶，
     桶内累加该 token 的 TF 权重（词频），避免维护词表；
  3) L2 归一化 → 向量内积即余弦相似度。

可替换位：若接入 bge-small-zh 等 Embedding 模型或大模型 API embedding，
只需实现同样的 encode(text)->np.ndarray 接口替换本类。
"""
import hashlib

import jieba
import numpy as np

DIM = 1024
STOPWORDS = {
    "的", "了", "和", "与", "及", "或", "在", "是", "为", "对", "将", "把",
    "被", "由", "从", "到", "等", "等语", "并", "而", "其", "该", "此",
    "一个", "一种", "进行", "通过", "可以", "需要", "以及", "如果", "则",
    "上", "下", "中", "内", "外", "都", "也", "就", "还", "又", "更",
}


def tokenize(text: str) -> list:
    """中文分词 + 停用词/单字过滤"""
    words = [w.strip().lower() for w in jieba.lcut(text)]
    return [w for w in words if w and w not in STOPWORDS and len(w) > 1]


def _hash_bucket(token: str, dim: int = DIM) -> int:
    """确定性哈希：token → 桶号 [0, dim)"""
    h = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") % dim


def encode(text: str, dim: int = DIM) -> np.ndarray:
    """文本 → L2 归一化向量（TF 权重 + 特征哈希）"""
    vec = np.zeros(dim, dtype=np.float32)
    for token in tokenize(text):
        vec[_hash_bucket(token, dim)] += 1.0          # TF 累加
    norm = np.linalg.norm(vec)
    if norm > 1e-12:
        vec /= norm
    return vec


def vector_to_json(vec: np.ndarray) -> str:
    """向量 → JSON 字符串（存储用，保留 4 位小数）"""
    import json
    return json.dumps([round(float(v), 4) for v in vec])


def vector_from_json(s: str) -> np.ndarray:
    import json
    return np.array(json.loads(s), dtype=np.float32)
