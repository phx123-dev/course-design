# -*- coding: utf-8 -*-
"""健康看板聚合接口：统计卡片 / 健康分布 / 预警趋势 / 设备健康列表"""
import datetime
import time

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import (Alarm, Equipment, Prediction, SensorSample, User, WorkOrder,
                    get_db)
from app.services import device_service
from app.services.stream_service import stream_engine

router = APIRouter(prefix="/api/dashboard", tags=["健康看板"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """看板一次性聚合：统计数据 + 健康分布 + 近 24h 预警趋势 + 设备列表"""
    devices = db.query(Equipment).order_by(Equipment.id).all()

    # ---- 统计卡片 ----
    fault_count = sum(1 for d in devices if d.health_state != 0)
    active_alarms = db.query(Alarm).filter(Alarm.status == "active").count()
    pending_wo = db.query(WorkOrder).filter(WorkOrder.status == "待处理").count()
    stats = {
        "device_total": len(devices),
        "device_running": sum(1 for d in devices if d.status == "运行"),
        "device_healthy": len(devices) - fault_count,
        "device_fault": fault_count,
        "active_alarms": active_alarms,
        "pending_workorders": pending_wo,
        "stream_running": stream_engine.running,
    }

    # ---- 健康分布（饼图） ----
    dist = {0: 0, 1: 0, 2: 0, 3: 0}
    for d in devices:
        dist[d.health_state] = dist.get(d.health_state, 0) + 1
    health_dist = [
        {"name": "正常", "value": dist[0]},
        {"name": "内圈故障", "value": dist[1]},
        {"name": "外圈故障", "value": dist[2]},
        {"name": "滚动体故障", "value": dist[3]},
    ]

    # ---- 近 24h 预警趋势（按小时分组） ----
    since = datetime.datetime.now() - datetime.timedelta(hours=24)
    rows = (db.query(func.strftime("%H", Alarm.created_at).label("h"),
                     func.count(Alarm.id))
            .filter(Alarm.created_at >= since)
            .group_by("h").all())
    hour_map = {h: c for h, c in rows}
    alarms_trend = [{"hour": f"{i:02d}:00", "count": hour_map.get(f"{i:02d}", 0)}
                    for i in range(24)]

    # ---- 设备健康列表（合并最新采样与最新预测） ----
    latest_pred = {}
    for p in db.query(Prediction).order_by(Prediction.id.desc()).limit(200).all():
        latest_pred.setdefault(p.device_id, p)
    device_list = []
    for d in devices:
        item = device_service.device_dict(d)
        last = stream_engine.last_samples.get(d.id)
        item["last_sample"] = last
        p = latest_pred.get(d.id)
        item["last_prediction"] = {
            "pred_class": p.pred_class, "health_score": p.health_score,
            "prob_normal": p.prob_normal, "prob_inner": p.prob_inner,
            "prob_outer": p.prob_outer, "prob_ball": p.prob_ball,
            "rul_hours": p.rul_hours, "ts": p.ts,
        } if p else None
        device_list.append(item)

    # ---- 最新预警 5 条 ----
    from app.services import alarm_service
    recent_alarms = alarm_service.list_alarms(db, limit=5)

    return ok({
        "stats": stats, "health_dist": health_dist, "alarms_trend": alarms_trend,
        "device_list": device_list, "recent_alarms": recent_alarms,
    })
