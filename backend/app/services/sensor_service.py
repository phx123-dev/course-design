# -*- coding: utf-8 -*-
"""传感器数据查询服务：时序曲线 / 波形+频谱回放 / 实时快照"""
import time

import numpy as np
from sqlalchemy.orm import Session

from app.db import SensorSample
from app.services.signal_gen import FS, characteristic_frequencies, stream_window


def timeseries(db: Session, device_id: int, window: int = 60, end_ts: float = None) -> list:
    """最近 window 秒的采样序列（升序）"""
    end_ts = end_ts or time.time()
    rows = (db.query(SensorSample)
            .filter(SensorSample.device_id == device_id, SensorSample.ts >= end_ts - window)
            .order_by(SensorSample.ts.asc()).all())
    return [{
        "ts": r.ts, "rms": r.vibration_rms, "peak": r.vibration_peak,
        "temp": r.temperature, "rpm": r.rpm, "fault_class": r.fault_class,
    } for r in rows]


def waveform_with_spectrum(db: Session, device_id: int, ts: float = None,
                           fault_class: int = None, rpm: float = None) -> dict:
    """波形确定性回放 + FFT 频谱。

    波形由 (设备, 时刻) 种子确定性生成（不入库）；
    频谱用与特征工程一致的汉宁窗 FFT，前端展示时域波形与特征频带。
    """
    ts = ts or time.time()
    from app.db import Equipment
    dev = db.query(Equipment).filter_by(id=device_id).first()
    fc = fault_class if fault_class is not None else (dev.health_state if dev else 0)
    rpm = rpm or (dev.rpm if dev else 1750.0)

    sig = stream_window(device_id, fc, ts=ts, rpm=rpm)
    n = len(sig)
    window = np.hanning(n)
    spectrum = np.fft.rfft(sig * window)
    freqs = np.fft.rfftfreq(n, d=1.0 / FS)
    mag = np.abs(spectrum)
    # 频谱抽稀（前端点太多无意义，保留低频 0-1000Hz 全谱 + 高频抽稀）
    mask = freqs <= 1000
    freqs_l, mag_l = freqs[mask], mag[mask]
    step = max(1, len(freqs_l) // 800)
    freqs_l, mag_l = freqs_l[::step], mag_l[::step]

    cf = characteristic_frequencies(rpm)
    return {
        "ts": ts, "fault_class": fc, "rpm": rpm,
        "sample_rate": FS,
        "time": [round(float(v), 5) for v in sig[:800]],      # 显示前 800 点
        "values": [round(float(v), 4) for v in sig[:800]],
        "freq": [round(float(v), 2) for v in freqs_l],
        "mag": [round(float(v), 3) for v in mag_l],
        "char_freqs": {k: round(v, 2) for k, v in cf.items()},
    }


def realtime_snapshot() -> list:
    """所有设备最新采样（前端轮询兜底，WebSocket 断开时使用）"""
    from app.services.stream_service import stream_engine
    return sorted(stream_engine.last_samples.values(), key=lambda x: x["device_id"])
