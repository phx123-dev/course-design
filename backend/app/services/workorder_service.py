# -*- coding: utf-8 -*-
"""维护工单服务：CRUD + 状态流转 + 诊断自动派单"""
import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import Equipment, WorkOrder

ALLOWED_STATUS = ("待处理", "进行中", "已完成")


def workorder_dict(wo: WorkOrder, device: Equipment = None) -> dict:
    return {
        "id": wo.id, "order_no": wo.order_no, "device_id": wo.device_id,
        "device_name": device.name if device else "",
        "title": wo.title, "wtype": wo.wtype, "description": wo.description,
        "priority": wo.priority, "status": wo.status, "source": wo.source,
        "diagnostic_id": wo.diagnostic_id, "assignee": wo.assignee,
        "created_at": wo.created_at.strftime("%Y-%m-%d %H:%M:%S") if wo.created_at else "",
        "started_at": wo.started_at.strftime("%Y-%m-%d %H:%M:%S") if wo.started_at else "",
        "finished_at": wo.finished_at.strftime("%Y-%m-%d %H:%M:%S") if wo.finished_at else "",
    }


def _next_order_no(db: Session) -> str:
    today = datetime.date.today().strftime("%Y%m%d")
    cnt = db.query(WorkOrder).filter(WorkOrder.order_no.like(f"WO-{today}-%")).count()
    return f"WO-{today}-{cnt + 1:04d}"


def list_workorders(db: Session, status: str = None, device_id: int = None,
                    limit: int = 100) -> list:
    q = db.query(WorkOrder)
    if status:
        q = q.filter(WorkOrder.status == status)
    if device_id:
        q = q.filter(WorkOrder.device_id == device_id)
    rows = q.order_by(WorkOrder.id.desc()).limit(min(limit, 500)).all()
    names = {d.id: d.name for d in db.query(Equipment).all()}
    return [workorder_dict(wo) | {"device_name": names.get(wo.device_id, "")}
            for wo in rows]


def create_workorder(db: Session, data: dict) -> dict:
    """创建工单。source=diagnosis 时为智能诊断自动派单。"""
    dev = db.query(Equipment).filter_by(id=data["device_id"]).first()
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    wo = WorkOrder(
        order_no=_next_order_no(db),
        device_id=data["device_id"], title=data.get("title", ""),
        wtype=data.get("wtype", "维修"), description=data.get("description", ""),
        priority=data.get("priority", "中"), source=data.get("source", "manual"),
        diagnostic_id=data.get("diagnostic_id"), assignee=data.get("assignee", ""),
    )
    db.add(wo)
    db.commit()
    return workorder_dict(wo, dev)


def update_status(db: Session, workorder_id: int, status: str) -> dict:
    """状态流转：待处理 → 进行中 → 已完成（记录各节点时间）"""
    if status not in ALLOWED_STATUS:
        raise HTTPException(status_code=400, detail=f"非法状态 {status}")
    wo = db.query(WorkOrder).filter_by(id=workorder_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    wo.status = status
    now = datetime.datetime.now()
    if status == "进行中" and not wo.started_at:
        wo.started_at = now
    if status == "已完成" and not wo.finished_at:
        wo.finished_at = now
    db.commit()
    return workorder_dict(wo)
