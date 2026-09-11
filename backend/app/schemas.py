# -*- coding: utf-8 -*-
"""Pydantic 请求/响应模型（接口契约，与前端约定先行）"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------- 认证 ----------------
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    display_name: str = ""


class LoginResponse(BaseModel):
    token: str
    user: UserInfo


# ---------------- 设备台账 ----------------
class EquipmentIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    etype: str = "旋转机械"
    location: str = ""
    commission_date: str = ""
    rpm: float = 1750.0
    load_ratio: float = 0.8
    health_state: int = Field(0, ge=0, le=3)
    status: str = "运行"
    description: str = ""


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    etype: Optional[str] = None
    location: Optional[str] = None
    commission_date: Optional[str] = None
    rpm: Optional[float] = None
    load_ratio: Optional[float] = None
    health_state: Optional[int] = Field(None, ge=0, le=3)
    status: Optional[str] = None
    description: Optional[str] = None


# ---------------- 监测/故障注入 ----------------
class FaultInjectIn(BaseModel):
    device_id: int
    fault_class: int = Field(1, ge=0, le=3)   # 0 恢复正常，1-3 注入故障


# ---------------- 知识库 ----------------
class KnowledgeSearchIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)


# ---------------- 对话 ----------------
class ChatCreateIn(BaseModel):
    device_id: Optional[int] = None
    title: str = "新对话"


class ChatSendIn(BaseModel):
    session_id: Optional[int] = None
    device_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=2000)


# ---------------- 工单 ----------------
class WorkOrderIn(BaseModel):
    device_id: int
    title: str = Field(..., min_length=1, max_length=200)
    wtype: str = "维修"          # 点检/维修/润滑/更换
    description: str = ""
    priority: str = "中"         # 高/中/低
    assignee: str = ""


class WorkOrderStatusIn(BaseModel):
    status: str = Field(..., pattern="^(待处理|进行中|已完成)$")


# ---------------- 统一响应 ----------------
def ok(data=None, **extra):
    """统一成功响应包装：{code:0, data:...}"""
    return {"code": 0, "data": data, **extra}
