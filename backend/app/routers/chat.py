# -*- coding: utf-8 -*-
"""对话接口：会话管理 + SSE 流式问诊（多智能体编排入口）"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import ChatMessage, ChatSession, User, get_db
from app.schemas import ChatCreateIn, ChatSendIn, ok
from app.services.agents.orchestrator import run_diagnosis
from app.services.agents.state import AgentState

router = APIRouter(prefix="/api/chat", tags=["智能诊断对话"])


def _session_dict(s: ChatSession, db: Session) -> dict:
    last = (db.query(ChatMessage).filter_by(session_id=s.id)
            .order_by(ChatMessage.id.desc()).first())
    return {
        "id": s.id, "device_id": s.device_id, "title": s.title,
        "mode": s.mode, "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "last_message": last.content[:60] if last else "",
    }


@router.post("/sessions")
def create_session(body: ChatCreateIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    s = ChatSession(user_id=user.id, device_id=body.device_id, title=body.title)
    db.add(s)
    db.commit()
    return ok(_session_dict(s, db))


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(ChatSession).filter_by(user_id=user.id)
            .order_by(ChatSession.id.desc()).limit(30).all())
    return ok([_session_dict(s, db) for s in rows])


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    rows = (db.query(ChatMessage).filter_by(session_id=session_id)
            .order_by(ChatMessage.id.asc()).all())
    return ok([{
        "id": m.id, "role": m.role, "content": m.content,
        "evidence": json.loads(m.evidence_json) if m.evidence_json else [],
        "diagnostic_id": m.diagnostic_id,
        "created_at": m.created_at.strftime("%H:%M:%S") if m.created_at else "",
    } for m in rows])


@router.post("/messages")
def send_message(body: ChatSendIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """SSE 流式问诊：多智能体编排逐步推送事件（前端展示过程与打字机回复）"""
    # 会话：指定则复用，否则新建
    session = None
    if body.session_id:
        session = db.query(ChatSession).filter_by(id=body.session_id,
                                                  user_id=user.id).first()
    if not session:
        session = ChatSession(user_id=user.id,
                              device_id=body.device_id or None,
                              title=body.message[:20])
        db.add(session)
        db.commit()

    # 用户消息先入库
    db.add(ChatMessage(session_id=session.id, role="user", content=body.message))
    db.commit()

    state = AgentState(session_id=session.id, user_id=user.id,
                       device_id=body.device_id or session.device_id,
                       query=body.message)

    def sse_events():
        try:
            for event, data in run_diagnosis(db, state):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:      # 编排异常兜底：给前端可展示的错误事件
            import traceback
            traceback.print_exc()
            err = {"event": "error", "data": {"message": f"诊断服务异常: {e}"}}
            yield f"event: error\ndata: {json.dumps(err['data'], ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
