# -*- coding: utf-8 -*-
"""
智能体工具层 —— 各节点调用的"工具"（tool calling 的本地实现）
==============================================================
LLM 模式中这些工具以"函数描述 + 执行结果"形式注入上下文；
离线模式中节点直接调用。所有工具返回可 JSON 序列化的字典。
"""
import time

import numpy as np
from sqlalchemy.orm import Session

from app.db import Alarm, Equipment, SensorSample, WorkOrder
from app.services.ml.features import extract_features, features_to_dict
from app.services.ml.predict import predict_health
from app.services.rag.retriever import search
from app.services.rag.store import load_index
from app.services.signal_gen import stream_window

# 工具清单（供 LLM 提示词描述能力边界）
TOOL_DESCRIPTIONS = """
可用工具：
1. get_device(device_id)：查询设备台账信息（型号/转速/位置/当前健康状态）
2. get_recent_data(device_id, seconds)：拉取最近传感器采样序列（RMS/峰值/温度）
3. get_features(device_id)：对当前波形提取时域/频域 14 维特征
4. run_prediction(device_id)：调用机器学习故障分类模型（XGBoost/随机森林），返回四类概率与健康评分
5. search_knowledge(query, top_k)：RAG 检索知识库（手册/SOP/维修案例），返回带来源与相似度的引用块
6. create_work_order(device_id, title, description, priority)：生成维护工单
"""


def get_device(db: Session, device_id: int) -> dict:
    from app.services.device_service import device_dict
    d = db.query(Equipment).filter_by(id=device_id).first()
    return device_dict(d) if d else {}


def get_recent_data(db: Session, device_id: int, seconds: int = 60) -> dict:
    rows = (db.query(SensorSample)
            .filter(SensorSample.device_id == device_id,
                    SensorSample.ts >= time.time() - seconds)
            .order_by(SensorSample.ts.desc()).limit(120).all())
    if not rows:
        return {"samples": [], "note": "暂无采样数据（数据流引擎未运行？）"}
    rms_list = [r.vibration_rms for r in rows]
    temp_list = [r.temperature for r in rows]
    return {
        "samples": [{"ts": r.ts, "rms": r.vibration_rms, "peak": r.vibration_peak,
                     "temp": r.temperature, "fault_class": r.fault_class} for r in rows],
        "stats": {
            "rms_mean": round(float(np.mean(rms_list)), 4),
            "rms_max": round(float(np.max(rms_list)), 4),
            "rms_min": round(float(np.min(rms_list)), 4),
            "temp_mean": round(float(np.mean(temp_list)), 2),
            "temp_max": round(float(np.max(temp_list)), 2),
            "count": len(rows),
        },
    }


def get_features(db: Session, device_id: int) -> dict:
    dev = db.query(Equipment).filter_by(id=device_id).first()
    if not dev:
        return {}
    win = stream_window(device_id, dev.health_state, ts=time.time(), rpm=dev.rpm)
    vec = extract_features(win, 12000, dev.rpm)
    return {"features": features_to_dict(vec), "rpm": dev.rpm}


def run_prediction(db: Session, device_id: int) -> dict:
    dev = db.query(Equipment).filter_by(id=device_id).first()
    if not dev:
        return {"available": False}
    win = stream_window(device_id, dev.health_state, ts=time.time(), rpm=dev.rpm)
    return predict_health(db, device_id, win, dev.rpm)


def search_knowledge(db: Session, query: str, top_k: int = 3) -> list:
    """RAG 检索：返回 [编号] 引用块（含来源与相似度）"""
    index = load_index(db)
    results = search(index, query, top_k=top_k)
    return [{"ref": r["ref"], "title": r["doc_title"], "source": r["doc_source"],
             "text": r["text"], "score": r["score"]} for r in results]


def create_work_order(db: Session, device_id: int, title: str, description: str,
                      priority: str = "中", wtype: str = "维修",
                      source: str = "diagnosis", diagnostic_id: int = None) -> dict:
    """生成维护工单（编号 WO-YYYYMMDD-序号）"""
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    cnt = db.query(WorkOrder).filter(WorkOrder.order_no.like(f"WO-{today}-%")).count()
    order_no = f"WO-{today}-{cnt + 1:04d}"
    wo = WorkOrder(order_no=order_no, device_id=device_id, title=title,
                   wtype=wtype, description=description, priority=priority,
                   source=source, diagnostic_id=diagnostic_id)
    db.add(wo)
    db.commit()
    return {"id": wo.id, "order_no": order_no, "status": wo.status}


def get_active_alarms(db: Session, device_id: int, limit: int = 5) -> list:
    rows = (db.query(Alarm).filter_by(device_id=device_id, status="active")
            .order_by(Alarm.id.desc()).limit(limit).all())
    return [{"type": a.alarm_type, "level": a.level, "message": a.message,
             "value": a.value} for a in rows]
