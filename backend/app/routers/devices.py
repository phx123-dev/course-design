# -*- coding: utf-8 -*-
"""设备台账接口：增删改查（写操作限 admin 角色）"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import User, get_db
from app.schemas import EquipmentIn, EquipmentUpdate, ok
from app.services import device_service

router = APIRouter(prefix="/api/devices", tags=["设备台账"])


@router.get("")
def list_devices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """设备列表（所有登录角色可读）"""
    return ok(device_service.list_devices(db))


@router.get("/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    return ok(device_service.device_dict(device_service.get_device(db, device_id)))


@router.post("")
def create_device(body: EquipmentIn, db: Session = Depends(get_db),
                  user: User = Depends(require_role("admin"))):
    """新增设备（仅系统管理员）"""
    return ok(device_service.create_device(db, body.model_dump()))


@router.put("/{device_id}")
def update_device(device_id: int, body: EquipmentUpdate, db: Session = Depends(get_db),
                  user: User = Depends(require_role("admin"))):
    """修改设备（仅系统管理员）"""
    return ok(device_service.update_device(db, device_id, body.model_dump(exclude_unset=True)))


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_role("admin"))):
    """删除设备（仅系统管理员）"""
    device_service.delete_device(db, device_id)
    return ok()
