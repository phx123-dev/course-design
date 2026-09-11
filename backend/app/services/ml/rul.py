# -*- coding: utf-8 -*-
"""
剩余寿命估计（RUL） —— 健康指标退化趋势线性外推
================================================
思路（数据驱动退化模型）：
  1) 定义健康指标 HI：由振动 RMS 归一化得到
       HI = 1 - (rms - rms_normal) / (rms_fail - rms_normal)，截断到 [0,1]
       （rms_normal 为正常基线，rms_fail 为失效阈值时的 RMS，由仿真退化数据统计）
  2) 取该设备近期 HI 序列，最小二乘线性拟合退化斜率 k（HI/秒）；
  3) 失效判据 HI ≤ HI_fail（默认 0.15），则
       RUL(小时) = (HI_now - HI_fail) / |k| / 3600
     斜率趋近 0（无退化趋势）时返回 None 表示"未检测到退化"。

说明：本课设数据为模拟信号，HI 通过确定性退化序列标定；
接入真实产线数据时可替换为真实退化曲线拟合（方法不变）。
"""
import time

import numpy as np
from sqlalchemy.orm import Session

from app.db import SensorSample
from app.services.signal_gen import synth_degradation_series

HI_FAIL = 0.15          # 失效健康指标阈值
FIT_MIN_POINTS = 10     # 最少历史点数才拟合


def calibrate_rms_bounds(fault_class: int, device_id: int = 0) -> tuple:
    """标定 (rms_normal, rms_fail)：由确定性退化序列统计得到

    - rms_normal：严重度为 0 时的 RMS（退化起点）
    - rms_fail  ：严重度为 1 时的 RMS（失效终点）
    """
    series = synth_degradation_series(fault_class, n_steps=20, seed=device_id)
    rms_list = [float(np.sqrt(np.mean(np.square(s)))) for s in series]
    return rms_list[0], rms_list[-1]


def health_index(rms: float, rms_normal: float, rms_fail: float) -> float:
    if rms_fail <= rms_normal + 1e-12:
        return 1.0
    return float(np.clip(1 - (rms - rms_normal) / (rms_fail - rms_normal), 0.0, 1.0))


def estimate_rul(db: Session, device_id: int, fault_class: int,
                 current_rms: float, lookback_points: int = 30) -> dict:
    """基于近期采样序列的线性退化外推。

    返回 {rul_hours, hi_now, slope_per_hour, degrading, fitted_points}
    rul_hours 为 None 表示未检测到退化（设备健康或数据不足）。
    """
    rms_normal, rms_fail = calibrate_rms_bounds(fault_class, device_id)

    # 取最近 lookback_points 条采样（模拟数据 1s 一条）
    rows = (db.query(SensorSample)
            .filter(SensorSample.device_id == device_id,
                    SensorSample.fault_class == fault_class)
            .order_by(SensorSample.id.desc())
            .limit(lookback_points).all())

    hi_now = health_index(current_rms, rms_normal, rms_fail)

    # 历史点数不足或当前无退化 → 不做外推
    if len(rows) < FIT_MIN_POINTS or fault_class == 0:
        return {"rul_hours": None, "hi_now": round(hi_now, 3),
                "slope_per_hour": 0.0, "degrading": False,
                "fitted_points": len(rows)}

    # 用历史 RMS 算 HI 序列（注意 rows 是倒序，先反转为时间升序）
    # 时间轴用真实采样时间戳（小时），保证不同采样间隔下斜率物理一致
    asc = list(reversed(rows))
    hi_series = [health_index(r.vibration_rms, rms_normal, rms_fail) for r in asc]
    hi_series.append(hi_now)
    t0 = asc[0].ts
    t_hours = np.array([(r.ts - t0) / 3600.0 for r in asc] + [(time.time() - t0) / 3600.0])
    if t_hours[-1] <= 1e-9:                # 全部同一时刻（无法拟合）
        return {"rul_hours": None, "hi_now": round(hi_now, 3),
                "slope_per_hour": 0.0, "degrading": False,
                "fitted_points": len(hi_series)}
    k = np.polyfit(t_hours, hi_series, 1)[0]   # 最小二乘线性拟合斜率（HI/小时）

    degrading = k < -1e-4                  # 显著下降趋势才算退化
    slope_per_hour = k
    if degrading:
        rul_hours = max(0.0, (hi_now - HI_FAIL) / (-k))   # (HI-阈值)/|斜率|，单位小时
    else:
        rul_hours = None
    return {"rul_hours": round(rul_hours, 1) if rul_hours is not None else None,
            "hi_now": round(hi_now, 3), "slope_per_hour": round(slope_per_hour, 4),
            "degrading": degrading, "fitted_points": len(hi_series)}
