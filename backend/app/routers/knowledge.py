# -*- coding: utf-8 -*-
"""知识库管理接口：语料上传 / 文档列表 / 统计 / 检索测试"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import KnowledgeDoc, User, get_db
from app.schemas import KnowledgeSearchIn, ok
from app.services.rag import store
from app.services.rag.retriever import search

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


@router.get("/docs")
def list_docs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(KnowledgeDoc).order_by(KnowledgeDoc.id.desc()).all()
    return ok([{
        "id": d.id, "title": d.title, "source": d.source,
        "chunk_count": d.chunk_count,
        "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "",
    } for d in rows])


@router.get("/stats")
def kb_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = store.stats(db)
    from app.services.rag import vectorizer
    return ok({**s, "vector_dim": vectorizer.DIM, "engine": "numpy+特征哈希（可替换 Chroma/Embedding）"})


@router.post("/search")
def kb_search(body: KnowledgeSearchIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """检索测试：返回 Top-K 结果（含引用编号/来源/分数），供前端与智能体使用"""
    index = store.load_index(db)
    results = search(index, body.query, top_k=body.top_k)
    return ok([{
        "ref": r["ref"], "title": r["doc_title"], "source": r["doc_source"],
        "text": r["text"][:300], "score": r["score"],
        "char_start": r["char_start"], "char_end": r["char_end"],
    } for r in results])


@router.post("/upload")
def upload(body: dict, db: Session = Depends(get_db),
           user: User = Depends(require_role("admin", "engineer"))):
    """上传/更新语料（markdown 文本；同标题视为更新）"""
    title = str(body.get("title", "")).strip()
    text = str(body.get("text", "")).strip()
    if not title or not text:
        return ok(None, code=400, message="标题与内容不能为空")
    result = store.add_document(db, title, text, str(body.get("source", "手动上传")))
    return ok(result)


@router.delete("/docs/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_role("admin"))):
    from app.db import KnowledgeChunk
    doc = db.query(KnowledgeDoc).filter_by(id=doc_id).first()
    if not doc:
        return ok(None, code=404, message="文档不存在")
    db.query(KnowledgeChunk).filter_by(doc_id=doc_id).delete()
    db.delete(doc)
    db.commit()
    return ok()
