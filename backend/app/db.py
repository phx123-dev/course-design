# -*- coding: utf-8 -*-
"""
数据库层 —— SQLAlchemy ORM，13 张表（SQLite，可平滑切换 MySQL）
==============================================================
表清单（按业务域分组）：
  认证域   : users(用户) auth_tokens(会话令牌)
  设备域   : equipment(设备台账) sensor_samples(时序采样) alarms(预警)
  智能域   : ml_models(模型登记) predictions(预测结果) diagnostic_records(诊断记录)
  业务域   : work_orders(维护工单)
  知识域   : knowledge_docs(知识文档) knowledge_chunks(知识分块含向量)
  对话域   : chat_sessions(会话) chat_messages(消息)
"""
import datetime
import json

import numpy as np
from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                        Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import DB_PATH

Base = declarative_base()


# ---------------------------- 认证域 ----------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)   # pbkdf2 加盐哈希
    role = Column(String(20), nullable=False, default="engineer")  # engineer|manager|admin
    display_name = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.now)


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)  # HMAC 摘要
    created_at = Column(DateTime, default=datetime.datetime.now)
    expires_at = Column(DateTime, nullable=False)


# ---------------------------- 设备域 ----------------------------
class Equipment(Base):
    __tablename__ = "equipment"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)      # 设备编号 EQ-001
    name = Column(String(100), nullable=False)                  # 设备名称
    etype = Column(String(50), default="旋转机械")               # 设备类型
    location = Column(String(100), default="")                  # 安装位置
    commission_date = Column(String(20), default="")
    rpm = Column(Float, default=1750.0)                         # 额定转速
    load_ratio = Column(Float, default=0.8)                     # 当前负载率
    health_state = Column(Integer, default=0)                   # 当前健康状态 0-3（与故障类别一致）
    status = Column(String(20), default="运行")                 # 运行/停机
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.now)


class SensorSample(Base):
    """时序采样表：流引擎每秒落一条聚合值（波形不落库，按需确定性回放）"""
    __tablename__ = "sensor_samples"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    ts = Column(Float, nullable=False, index=True)              # Unix 时间戳
    rpm = Column(Float, default=0.0)
    vibration_rms = Column(Float, default=0.0)                  # 振动有效值
    vibration_peak = Column(Float, default=0.0)                 # 振动峰值
    temperature = Column(Float, default=0.0)                    # 轴承温度
    fault_class = Column(Integer, default=0)                    # 该时刻真实状态（演示用标签）

    __table_args__ = ()


class Alarm(Base):
    __tablename__ = "alarms"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    alarm_type = Column(String(50), default="")                 # 3σ异常/隔离森林/温度超限
    level = Column(Integer, default=1)                          # 1提示 2警告 3严重
    message = Column(Text, default="")
    value = Column(Float, default=0.0)
    status = Column(String(20), default="active")               # active|acked|closed
    created_at = Column(DateTime, default=datetime.datetime.now)
    acked_at = Column(DateTime, nullable=True)


# ---------------------------- 智能域 ----------------------------
class MLModel(Base):
    __tablename__ = "ml_models"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    algorithm = Column(String(50), default="")                  # XGBoost / RandomForest / GradientBoosting
    version = Column(String(20), default="v1")
    accuracy = Column(Float, default=0.0)
    metrics_json = Column(Text, default="{}")                   # 完整评测指标
    path = Column(String(200), default="")                      # 模型文件路径
    trained_at = Column(DateTime, default=datetime.datetime.now)
    is_active = Column(Integer, default=1)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    ts = Column(Float, nullable=False, index=True)
    prob_normal = Column(Float, default=0.0)
    prob_inner = Column(Float, default=0.0)
    prob_outer = Column(Float, default=0.0)
    prob_ball = Column(Float, default=0.0)
    pred_class = Column(Integer, default=0)                     # 预测类别
    health_score = Column(Float, default=100.0)                 # 健康评分 0-100
    rul_hours = Column(Float, default=0.0)                      # 剩余寿命估计（小时，0=未启用）
    model_id = Column(Integer, ForeignKey("ml_models.id"), nullable=True)
    available = Column(Integer, default=1)                      # 模型是否可用（无模型时为 0）


class DiagnosticRecord(Base):
    """多智能体诊断记录：结论 + 依据 + 节点轨迹，全链路可溯源"""
    __tablename__ = "diagnostic_records"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=True)
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=True, index=True)
    conclusion_json = Column(Text, default="{}")                # {故障类型/置信度/原因/建议}
    evidence_json = Column(Text, default="[]")                  # 知识库引用 + 数据证据
    mode = Column(String(20), default="offline")                # llm|offline
    latency_ms = Column(Integer, default=0)                     # 端到端耗时（性能验收指标）
    trace_json = Column(Text, default="[]")                     # 各节点执行轨迹
    created_at = Column(DateTime, default=datetime.datetime.now)


# ---------------------------- 业务域 ----------------------------
class WorkOrder(Base):
    __tablename__ = "work_orders"
    id = Column(Integer, primary_key=True)
    order_no = Column(String(30), unique=True, nullable=False)  # WO-20260911-0001
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=False, index=True)
    title = Column(String(200), default="")
    wtype = Column(String(20), default="维修")                   # 点检/维修/润滑/更换
    description = Column(Text, default="")
    priority = Column(String(10), default="中")                  # 高/中/低
    status = Column(String(20), default="待处理", index=True)     # 待处理|进行中|已完成
    source = Column(String(20), default="manual")               # manual|auto|diagnosis
    diagnostic_id = Column(Integer, ForeignKey("diagnostic_records.id"), nullable=True)
    assignee = Column(String(50), default="")
    created_at = Column(DateTime, default=datetime.datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)


# ---------------------------- 知识域 ----------------------------
class KnowledgeDoc(Base):
    __tablename__ = "knowledge_docs"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    source = Column(String(100), default="自建语料")             # 来源说明
    raw_text = Column(Text, default="")
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id = Column(Integer, primary_key=True)
    doc_id = Column(Integer, ForeignKey("knowledge_docs.id"), nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    text = Column(Text, nullable=False)
    vector_blob = Column(Text, default="")                      # numpy 向量 JSON 字符串
    char_start = Column(Integer, default=0)                     # 原文字符起始位置（引用定位）
    char_end = Column(Integer, default=0)


# ---------------------------- 对话域 ----------------------------
class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("equipment.id"), nullable=True)  # 当前诊断对象
    title = Column(String(200), default="新对话")
    mode = Column(String(20), default="offline")                # 本会话实际运行模式
    created_at = Column(DateTime, default=datetime.datetime.now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)                   # user|assistant|system
    content = Column(Text, default="")
    evidence_json = Column(Text, default="[]")                  # 依据引用（知识来源+数据证据）
    diagnostic_id = Column(Integer, ForeignKey("diagnostic_records.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)


# ---------------------------- 引擎与工具函数 ----------------------------
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},   # 多线程访问（流引擎+API）
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI 依赖：每个请求一个独立会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表（幂等）"""
    Base.metadata.create_all(engine)


def seed_basic(session):
    """基础种子：3 个演示账号 + 设备台账（幂等，按唯一键跳过）"""
    from app.auth import hash_password
    users = [
        ("admin", "admin", "admin", "系统管理员"),
        ("engineer", "engineer", "engineer", "维护工程师"),
        ("manager", "manager", "manager", "车间管理员"),
    ]
    for username, role, _pwd, display in users:
        if not session.query(User).filter_by(username=username).first():
            session.add(User(username=username, role=role,
                             password_hash=hash_password("123456"),
                             display_name=display))

    devices = [
        ("EQ-001", "数控车床 CK6140 主轴轴承", "数控机床", "一号车间 A区", 1750, 0),
        ("EQ-002", "立式加工中心 VMC850 主轴轴承", "数控机床", "一号车间 A区", 2200, 0),
        ("EQ-003", "工业风机 Y4-73 轴承座", "风机", "一号车间 B区", 1450, 0),
        ("EQ-004", "输送机驱动电机 Y132M", "电机", "一号车间 C区", 1440, 0),
        ("EQ-005", "磨床 M7130 主轴轴承", "数控机床", "二号车间 A区", 2800, 0),
        ("EQ-006", "AGV 轮毂驱动电机", "电机", "物流通道", 1200, 0),
    ]
    for code, name, etype, loc, rpm, hs in devices:
        if not session.query(Equipment).filter_by(code=code).first():
            session.add(Equipment(code=code, name=name, etype=etype, location=loc,
                                  rpm=rpm, health_state=hs))
    session.commit()
