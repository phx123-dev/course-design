# -*- coding: utf-8 -*-
"""维护工单接口：列表 / 创建（含诊断自动派单）/ 状态流转"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import User, get_db
from app.schemas import WorkOrderIn, WorkOrderStatusIn, ok
from app.services import workorder_service

router = APIRouter(prefix="/api/workorders", tags=["维护工单"])


@router.get("")
def list_workorders(status: str = None, device_id: int = None, limit: int = 100,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    return ok(workorder_service.list_workorders(db, status=status,
                                                device_id=device_id, limit=limit))


@router.post("")
def create_workorder(body: WorkOrderIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """创建工单。诊断对话页"一键派单"传 source=diagnosis + diagnostic_id。"""
    return ok(workorder_service.create_workorder(db, body.model_dump()))


@router.put("/{workorder_id}/status")
def update_status(workorder_id: int, body: WorkOrderStatusIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return ok(workorder_service.update_status(db, workorder_id, body.status))
