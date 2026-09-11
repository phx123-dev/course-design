# -*- coding: utf-8 -*-
"""
向量存储 —— numpy 内存索引 + SQLite 持久化（可替换 Chroma 位）
==============================================================
存储结构：knowledge_docs（文档）+ knowledge_chunks（分块 + 向量 blob）
内存索引：启动时（或入库后）从 DB 加载全部向量拼成矩阵，检索一次矩阵乘法完成。
课设规模（<1 万 chunk）下性能充足；接口与向量库解耦，可替换 Chroma/FAISS。
"""
import numpy as np
from sqlalchemy.orm import Session

from app.db import KnowledgeChunk, KnowledgeDoc
from app.services.rag import splitter, vectorizer


def add_document(db: Session, title: str, text: str, source: str = "自建语料") -> dict:
    """文档入库：切分 → 向量化 → 写 chunks（幂等：同标题先删旧版）"""
    old = db.query(KnowledgeDoc).filter_by(title=title).first()
    if old:
        db.query(KnowledgeChunk).filter_by(doc_id=old.id).delete()
        db.delete(old)
        db.flush()

    doc = KnowledgeDoc(title=title, source=source, raw_text=text)
    db.add(doc)
    db.flush()
    parts = splitter.split_markdown(text)
    for i, p in enumerate(parts):
        vec = vectorizer.encode(p["text"])
        db.add(KnowledgeChunk(doc_id=doc.id, chunk_index=i, text=p["text"],
                              vector_blob=vectorizer.vector_to_json(vec),
                              char_start=p["char_start"], char_end=p["char_end"]))
    doc.chunk_count = len(parts)
    db.commit()
    return {"id": doc.id, "title": title, "chunk_count": len(parts)}


def load_index(db: Session) -> dict:
    """从 DB 加载全部向量与元信息到内存索引"""
    chunks = (db.query(KnowledgeChunk).join(KnowledgeDoc)
              .order_by(KnowledgeChunk.id).all())
    vectors, metas = [], []
    for c in chunks:
        v = vectorizer.vector_from_json(c.vector_blob)
        if len(v) != vectorizer.DIM:
            v = vectorizer.encode(c.text)      # 旧数据兜底重算
        vectors.append(v)
        metas.append({
            "chunk_id": c.id, "doc_id": c.doc_id, "doc_title": c.doc.title,
            "doc_source": c.doc.source, "text": c.text,
            "char_start": c.char_start, "char_end": c.char_end,
            "chunk_index": c.chunk_index,
        })
    return {
        "matrix": np.vstack(vectors) if vectors else np.zeros((0, vectorizer.DIM), dtype=np.float32),
        "metas": metas,
    }


def stats(db: Session) -> dict:
    """知识库统计：文档数/分块数/总字符"""
    docs = db.query(KnowledgeDoc).count()
    chunks = db.query(KnowledgeChunk).count()
    return {"doc_count": docs, "chunk_count": chunks}
