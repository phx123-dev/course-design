# -*- coding: utf-8 -*-
"""预警服务：列表 / 确认处理"""
import datetime

from sqlalchemy.orm import Session

from app.db import Alarm


def alarm_dict(a: Alarm, device_name: str = "") -> dict:
    return {
        "id": a.id, "device_id": a.device_id, "device_name": device_name,
        "type": a.alarm_type, "level": a.level, "message": a.message,
        "value": a.value, "status": a.status,
        "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
    }


def list_alarms(db: Session, status: str = None, limit: int = 50) -> list:
    from app.db import Equipment
    q = db.query(Alarm)
    if status:
        q = q.filter(Alarm.status == status)
    rows = q.order_by(Alarm.id.desc()).limit(limit).all()
    names = {d.id: d.name for d in db.query(Equipment).all()}
    return [alarm_dict(a, names.get(a.device_id, "")) for a in rows]


def ack_alarm(db: Session, alarm_id: int) -> dict:
    a = db.query(Alarm).filter_by(id=alarm_id).first()
    if not a:
        return None
    a.status = "closed"
    a.acked_at = datetime.datetime.now()
    db.commit()
    return alarm_dict(a)
