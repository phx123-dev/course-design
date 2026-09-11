# -*- coding: utf-8 -*-
"""设备台账业务服务：增删改查 + 健康状态中文标签映射"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import Equipment
from app.services.signal_gen import CLASS_LABELS_ZH

# 健康状态 → 展示信息（前端看板直接使用）
HEALTH_INFO = {
    0: {"label": "正常", "color": "#67C23A", "level": "good"},
    1: {"label": "内圈故障", "color": "#F56C6C", "level": "danger"},
    2: {"label": "外圈故障", "color": "#E6A23C", "level": "warning"},
    3: {"label": "滚动体故障", "color": "#F56C6C", "level": "danger"},
}


def device_dict(d: Equipment) -> dict:
    """ORM 对象 → 前端友好的字典（含健康状态中文标签）"""
    info = HEALTH_INFO.get(d.health_state, HEALTH_INFO[0])
    return {
        "id": d.id, "code": d.code, "name": d.name, "etype": d.etype,
        "location": d.location, "commission_date": d.commission_date,
        "rpm": d.rpm, "load_ratio": d.load_ratio,
        "health_state": d.health_state,
        "health_label": info["label"], "health_color": info["color"],
        "status": d.status, "description": d.description,
    }


def list_devices(db: Session) -> list:
    return [device_dict(d) for d in db.query(Equipment).order_by(Equipment.id).all()]


def get_device(db: Session, device_id: int) -> Equipment:
    d = db.query(Equipment).filter_by(id=device_id).first()
    if not d:
        raise HTTPException(status_code=404, detail=f"设备 {device_id} 不存在")
    return d


def create_device(db: Session, data: dict) -> dict:
    if db.query(Equipment).filter_by(code=data["code"]).first():
        raise HTTPException(status_code=400, detail=f"设备编号 {data['code']} 已存在")
    d = Equipment(**data)
    db.add(d)
    db.commit()
    return device_dict(d)


def update_device(db: Session, device_id: int, data: dict) -> dict:
    d = get_device(db, device_id)
    for k, v in data.items():
        if v is not None:
            setattr(d, k, v)
    db.commit()
    return device_dict(d)


def delete_device(db: Session, device_id: int) -> None:
    d = get_device(db, device_id)
    db.delete(d)
    db.commit()
