# -*- coding: utf-8 -*-
"""
混合检索 —— 向量余弦相似度 + 关键词命中加权
============================================
score = 0.7 * cosine(query, chunk) + 0.3 * keyword_overlap(query, chunk)

关键词项：query 与 chunk 的分词集合的 Jaccard 相似度，
         用于纠正特征哈希在短查询上的稀疏偏差（如"内圈"命中"内圈故障"）。

返回 Top-K：{title, source, text, score, char_start, char_end, ref}
ref 为 [编号] 引用序号，供大模型/前端溯源卡片使用。
"""
import numpy as np

from app.services.rag import vectorizer


def search(index: dict, query: str, top_k: int = 5) -> list:
    """混合检索主入口（index 由 store.load_index 提供）"""
    matrix, metas = index["matrix"], index["metas"]
    if len(metas) == 0:
        return []

    qv = vectorizer.encode(query)
    q_tokens = set(vectorizer.tokenize(query))

    cosine = matrix @ qv                       # L2 归一化后内积即余弦
    results = []
    for i, meta in enumerate(metas):
        kw = _keyword_overlap(q_tokens, vectorizer.tokenize(meta["text"]))
        score = 0.7 * float(cosine[i]) + 0.3 * kw
        results.append({**meta, "score": round(score, 4), "kw": round(kw, 4)})

    results.sort(key=lambda r: r["score"], reverse=True)
    # 同文档去重：每篇文档只保留得分最高的块，提升引用来源多样性
    seen_docs, top = set(), []
    for r in results:
        if r["doc_id"] in seen_docs:
            continue
        seen_docs.add(r["doc_id"])
        top.append(r)
        if len(top) >= top_k:
            break
    for i, r in enumerate(top):
        r["ref"] = f"[{i + 1}]"
    return top


def _keyword_overlap(q_tokens: set, c_tokens: list) -> float:
    """Jaccard 相似度：|交集| / |并集|"""
    if not q_tokens or not c_tokens:
        return 0.0
    c_set = set(c_tokens)
    inter = len(q_tokens & c_set)
    union = len(q_tokens | c_set)
    return inter / union if union else 0.0
