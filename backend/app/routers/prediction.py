# -*- coding: utf-8 -*-
"""机器学习预测接口：运行预测 / 历史记录 / 模型列表"""
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.db import MLModel, Prediction, User, get_db
from app.schemas import ok
from app.services.ml.predict import predict_health
from app.services.signal_gen import stream_window

router = APIRouter(prefix="/api", tags=["机器学习预测"])


@router.post("/prediction/{device_id}/run")
def run_prediction(device_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """对设备当前状态运行一次完整预测（取当前时刻波形窗口）"""
    from app.db import Equipment
    dev = db.query(Equipment).filter_by(id=device_id).first()
    if not dev:
        return ok(None, code=404, message="设备不存在")
    window = stream_window(device_id, dev.health_state, ts=time.time(), rpm=dev.rpm)
    result = predict_health(db, device_id, window, dev.rpm)
    return ok(result)


@router.post("/prediction/rul-demo")
def rul_demo(body: dict, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    """RUL 演示：构造 48 小时退化历史（每小时一个样本，仿真数据），
    以外圈故障为例估算剩余寿命。返回退化曲线与 RUL 外推结果。

    说明：本接口为算法演示用途，历史数据为合成退化序列（如实披露）。
    """
    from app.db import Equipment, SensorSample
    from app.services.ml.rul import estimate_rul, health_index
    from app.services.signal_gen import synth_degradation_series
    device_id = int(body.get("device_id", 1))
    fault_class = int(body.get("fault_class", 2))
    dev = db.query(Equipment).filter_by(id=device_id).first()
    rpm = dev.rpm if dev else 1750.0

    n = 48
    series = synth_degradation_series(fault_class, n_steps=n, seed=device_id * 7 + fault_class)
    base = time.time() - (n - 1) * 3600
    rms_list = []
    for i, s in enumerate(series):
        rms = float(np.sqrt(np.mean(np.square(s))))
        rms_list.append(rms)
        db.add(SensorSample(device_id=device_id, ts=base + i * 3600, rpm=rpm,
                            vibration_rms=round(rms, 4), vibration_peak=0,
                            temperature=50, fault_class=fault_class))
    db.commit()

    # 模拟"当前"处于全寿命 3/4 处（未失效，尚可外推）
    rms_normal = rms_list[0]
    rms_fail = rms_list[-1]
    now_rms = rms_list[36]
    res = estimate_rul(db, device_id, fault_class, now_rms)
    hi_series = [{"ts": base + i * 3600,
                  "hi": health_index(r, rms_normal, rms_fail)} for i, r in enumerate(rms_list)]
    return ok({
        "fault_class": fault_class, "rpm": rpm,
        "history": hi_series,
        "rul_hours": res["rul_hours"], "hi_now": res["hi_now"],
        "slope_per_hour": res["slope_per_hour"], "degrading": res["degrading"],
    })


@router.get("/prediction/history")
def prediction_history(device_id: int = None, limit: int = 20,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    q = db.query(Prediction)
    if device_id:
        q = q.filter(Prediction.device_id == device_id)
    rows = q.order_by(Prediction.id.desc()).limit(min(limit, 100)).all()
    from app.services.signal_gen import CLASS_NAMES_ZH
    return ok([{
        "id": p.id, "device_id": p.device_id, "ts": p.ts,
        "pred_class": p.pred_class, "pred_label": CLASS_NAMES_ZH[p.pred_class],
        "probs": [p.prob_normal, p.prob_inner, p.prob_outer, p.prob_ball],
        "health_score": p.health_score, "rul_hours": p.rul_hours,
        "available": bool(p.available),
    } for p in rows])


@router.get("/ml/models")
def list_models(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """已训练模型列表（含评测指标，供报告/前端展示）"""
    rows = db.query(MLModel).order_by(MLModel.id.desc()).all()
    return ok([{
        "id": m.id, "name": m.name, "algorithm": m.algorithm,
        "version": m.version, "accuracy": m.accuracy,
        "is_active": bool(m.is_active),
        "trained_at": m.trained_at.strftime("%Y-%m-%d %H:%M:%S") if m.trained_at else "",
    } for m in rows])
