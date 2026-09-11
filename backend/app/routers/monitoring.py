# -*- coding: utf-8 -*-
"""实时监测接口：流引擎控制 / 故障注入 / 时序与波形数据 / 预警管理"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import Equipment, User, get_db
from app.schemas import FaultInjectIn, ok
from app.services import alarm_service, sensor_service
from app.services.stream_service import stream_engine

monitor_router = APIRouter(prefix="/api/monitoring", tags=["实时监测"])
sensor_router = APIRouter(prefix="/api", tags=["传感器数据"])
alarm_router = APIRouter(prefix="/api/alarms", tags=["预警"])


@monitor_router.post("/start")
def start_stream(user: User = Depends(get_current_user)):
    """启动数据流引擎（幂等）"""
    stream_engine.start()
    return ok({"running": stream_engine.running})


@monitor_router.post("/stop")
def stop_stream(user: User = Depends(require_role("admin"))):
    """停止数据流引擎（仅管理员）"""
    stream_engine.stop()
    return ok({"running": stream_engine.running})


@monitor_router.get("/status")
def stream_status(user: User = Depends(get_current_user)):
    return ok({"running": stream_engine.running, "started_at": stream_engine.started_at})


@monitor_router.post("/inject-fault")
def inject_fault(body: FaultInjectIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """故障注入（演示用）：修改设备健康状态 → 流引擎自动产生对应故障信号。

    同时写入一条"状态变化"预警，模拟车间异常上报。
    """
    dev = db.query(Equipment).filter_by(id=body.device_id).first()
    if not dev:
        return ok(None, code=404, message="设备不存在")
    dev.health_state = body.fault_class
    db.commit()
    stream_engine.log_state_change(body.device_id, body.fault_class)
    # 确保流引擎在运行（看板/监控页数据来源）
    if not stream_engine.running:
        stream_engine.start()
    return ok({"device_id": body.device_id, "health_state": body.fault_class})


@monitor_router.get("/realtime")
def realtime(user: User = Depends(get_current_user)):
    """所有设备最新采样快照（WebSocket 断开时的轮询兜底）"""
    return ok(sensor_service.realtime_snapshot())


# ---------------- 传感器数据（设备维度） ----------------
@sensor_router.get("/devices/{device_id}/timeseries")
def timeseries(device_id: int, window: int = 60, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return ok(sensor_service.timeseries(db, device_id, window=min(window, 600)))


@sensor_router.get("/devices/{device_id}/waveform")
def waveform(device_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """波形 + 频谱确定性回放"""
    return ok(sensor_service.waveform_with_spectrum(db, device_id))


# ---------------- 预警管理 ----------------
@alarm_router.get("")
def list_alarms(status: str = None, limit: int = 50, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    return ok(alarm_service.list_alarms(db, status=status, limit=min(limit, 200)))


@alarm_router.post("/{alarm_id}/ack")
def ack_alarm(alarm_id: int, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    row = alarm_service.ack_alarm(db, alarm_id)
    if not row:
        return ok(None, code=404, message="预警不存在")
    return ok(row)
