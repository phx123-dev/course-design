# -*- coding: utf-8 -*-
"""
WebSocket 实时推送 —— /ws/device/{id}?token=<令牌>
====================================================
连接建立后每秒推送一次该设备的实时状态：
  {sample: 最新采样, health_state: 当前健康状态, alarm: 新预警(仅新产生时)}

认证：FastAPI WebSocket 无法使用 HTTP 依赖，token 走查询参数，
      用与 HTTP 接口相同的令牌摘要校验（见 auth.py）。
"""
import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app import auth as auth_mod
from app.db import Alarm, SessionLocal
from app.services.stream_service import stream_engine

router = APIRouter()


def _verify_token(token: str) -> bool:
    """校验查询参数令牌（复用 auth 的摘要机制）"""
    if not token:
        return False
    db = SessionLocal()
    try:
        row = db.query(auth_mod.AuthToken).filter_by(
            token=auth_mod._token_digest(token)).first()
        return bool(row)
    finally:
        db.close()


@router.websocket("/ws/device/{device_id}")
async def device_ws(ws: WebSocket, device_id: int, token: str = None):
    if not _verify_token(token):
        await ws.close(code=4401, reason="未授权")
        return
    await ws.accept()

    last_alarm_id = 0
    try:
        while True:
            db = SessionLocal()
            try:
                sample = stream_engine.last_samples.get(device_id)
                # 该设备的最新未处理预警（仅推送新增的）
                alarm = (db.query(Alarm).filter_by(device_id=device_id)
                         .filter(Alarm.id > last_alarm_id)
                         .order_by(Alarm.id.desc()).first())
                payload = {
                    "type": "tick",
                    "ts": time.time(),
                    "sample": sample,
                    "alarm": ({
                        "id": alarm.id, "type": alarm.alarm_type,
                        "level": alarm.level, "message": alarm.message,
                    } if alarm else None),
                }
                if alarm:
                    last_alarm_id = max(last_alarm_id, alarm.id)
            finally:
                db.close()
            await ws.send_text(json.dumps(payload, ensure_ascii=False))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] device {device_id} error: {e}")
