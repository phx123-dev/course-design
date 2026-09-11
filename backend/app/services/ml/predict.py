# -*- coding: utf-8 -*-
"""
预测服务 —— 模型加载 / 特征预测 / 健康评分 / 结果入库
======================================================
对外统一入口：predict_health(db, device_id, window: np.ndarray, rpm)
  1) 加载当前活跃模型（无模型文件时返回 available=False，不抛异常）；
  2) 提取 14 维特征 → 四类概率；
  3) 健康评分（按故障严重性加权）：外圈权重 0.5、内圈 0.2、滚动体 0.15；
  4) 调用 RUL 估计；
  5) 结果写入 predictions 表并返回（供前端与多智能体工具使用）。
"""
import time

import joblib
import numpy as np
from sqlalchemy.orm import Session

from app.db import MLModel, Prediction
from app.services.ml.features import extract_features
from app.services.ml.rul import estimate_rul

CLASS_NAMES_ZH = ["正常", "内圈故障", "外圈故障", "滚动体故障"]
SEVERITY_WEIGHT = {0: 1.0, 1: 0.2, 2: 0.5, 3: 0.15}   # 健康评分中各状态权重

_cached_model = None       # 进程内缓存（避免每次预测都读盘）
_cached_path = None


def _load_active_model(db: Session):
    """加载活跃模型（带缓存）"""
    global _cached_model, _cached_path
    row = db.query(MLModel).filter(MLModel.is_active == 1).order_by(MLModel.id.desc()).first()
    if not row:
        return None, None
    if _cached_path == row.path:
        return _cached_model, row
    model = joblib.load(row.path)
    _cached_model, _cached_path = model, row.path
    return model, row


def predict_health(db: Session, device_id: int, window: np.ndarray, rpm: float,
                   save: bool = True) -> dict:
    """健康预测主入口"""
    model, meta = _load_active_model(db)
    if model is None or meta is None:
        return {"available": False, "message": "模型未训练，请先运行 train.bat 或 seed_all.py --quick"}

    vec = extract_features(window, 12000, rpm)
    probs = model.predict_proba(vec.reshape(1, -1))[0]
    pred_class = int(np.argmax(probs))
    prob_map = {cls: float(probs[cls]) for cls in range(4)}

    # 健康评分：正常占满分，故障按严重性折算
    health_score = float(np.clip(
        100 * (prob_map[0] * SEVERITY_WEIGHT[0]
               + prob_map[1] * SEVERITY_WEIGHT[1]
               + prob_map[2] * SEVERITY_WEIGHT[2]
               + prob_map[3] * SEVERITY_WEIGHT[3]), 0, 100))

    # 剩余寿命估计（仅故障状态有意义）
    rms = float(np.sqrt(np.mean(np.square(window))))
    rul = estimate_rul(db, device_id, pred_class, rms) if pred_class != 0 else {"rul_hours": None, "degrading": False, "hi_now": 1.0}

    result = {
        "available": True,
        "model": meta.algorithm, "model_version": meta.version,
        "device_id": device_id, "ts": time.time(),
        "pred_class": pred_class, "pred_label": CLASS_NAMES_ZH[pred_class],
        "probs": {
            "正常": round(prob_map[0], 4), "内圈故障": round(prob_map[1], 4),
            "外圈故障": round(prob_map[2], 4), "滚动体故障": round(prob_map[3], 4),
        },
        "prob_normal": round(prob_map[0], 4),
        "prob_inner": round(prob_map[1], 4),
        "prob_outer": round(prob_map[2], 4),
        "prob_ball": round(prob_map[3], 4),
        "health_score": round(health_score, 1),
        "rul_hours": rul.get("rul_hours"),
        "degrading": rul.get("degrading", False),
        "hi_now": rul.get("hi_now", 1.0),
    }
    if save:
        db.add(Prediction(device_id=device_id, ts=result["ts"],
                          prob_normal=result["prob_normal"],
                          prob_inner=result["prob_inner"],
                          prob_outer=result["prob_outer"],
                          prob_ball=result["prob_ball"],
                          pred_class=pred_class, health_score=health_score,
                          rul_hours=result["rul_hours"] or 0.0,
                          model_id=meta.id, available=1))
        db.commit()
    return result
