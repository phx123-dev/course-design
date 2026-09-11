# -*- coding: utf-8 -*-
"""
实时数据流引擎 —— 后台线程模拟传感器采集
==========================================
- 每个 tick（默认 1s）为所有"运行"状态设备生成一段 0.25s 振动窗口，
  统计 RMS/峰值并合成轴承温度，写入 sensor_samples 表；
- 波形本身不落库（由 (设备,时间) 确定性回放，见 signal_gen.stream_window）；
- 单写线程：所有数据库写入都发生在本引擎线程内，避免 SQLite 写锁竞争；
- 每设备滚动保留 20000 条采样，超出自动清理，控制库体积；
- 每个 tick 调用异常监测器（3σ + 孤立森林 + 温度超限），触发则写 alarms 表。
"""
import threading
import time

import numpy as np

from app.db import (Alarm, Equipment, SensorSample, SessionLocal,
                    sessionmaker, engine)
from app.services.anomaly import DeviceAnomalyMonitor
from app.services.signal_gen import stream_window

TICK_INTERVAL = 1.0        # 采样周期（秒）
MAX_ROWS_PER_DEVICE = 20000


class StreamEngine:
    """单例流引擎"""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self.running = False
        self.started_at = None
        self.last_samples = {}       # device_id -> 最新采样字典（前端轮询实时接口）
        self._monitors = {}          # device_id -> DeviceAnomalyMonitor
        self._temps = {}             # device_id -> 当前温度（热惯性状态）

    # ---------- 对外控制 ----------
    def start(self):
        """启动流引擎（幂等）"""
        if self.running:
            return
        self._stop.clear()
        self.running = True
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="stream-engine")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.running = False

    # ---------- 内部 ----------
    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:   # 单 tick 异常不终止引擎（容错降级）
                print(f"[stream] tick error: {e}")
            self._stop.wait(TICK_INTERVAL)

    def _get_or_create_monitor(self, device_id: int) -> DeviceAnomalyMonitor:
        """每设备一个异常监测器；基线由正常工况模拟信号统计得到（确定性）"""
        if device_id in self._monitors:
            return self._monitors[device_id]
        # 正常工况下 40 段窗口的 RMS 统计 → 3σ 基线
        # 每段叠加轻微工况抖动（噪声/转速），使基线更接近真实传感器波动
        rms_baseline, iso_samples = [], []
        rng = np.random.default_rng(device_id)
        for i in range(40):
            sig = stream_window(device_id, 0, ts=1e9 + i, rpm=1750 + rng.uniform(-40, 40))
            rms = float(np.sqrt(np.mean(np.square(sig))))
            rms_baseline.append(rms)
            temp = 45.0 + 3.0 * rng.standard_normal()
            iso_samples.append([rms, temp])
        mon = DeviceAnomalyMonitor(rms_baseline, iso_samples)
        self._monitors[device_id] = mon
        return mon

    def _tick(self):
        db = SessionLocal()
        try:
            devices = db.query(Equipment).filter(Equipment.status == "运行").all()
            now = time.time()
            for d in devices:
                self._sample_device(db, d, now)
            db.commit()
        finally:
            db.close()

    def _sample_device(self, db, device: Equipment, now: float):
        """单设备采样 + 异常检测 + 滚动清理"""
        fault_class = device.health_state
        # 波形确定性回放：同 (设备, 时刻) 永远同波形
        sig = stream_window(device.id, fault_class, ts=now, rpm=device.rpm)
        rms = float(np.sqrt(np.mean(np.square(sig))))
        peak = float(np.max(np.abs(sig)))
        # 温度模型：基础温度 + 负载产热 + 振动摩擦产热（故障时显著升高），
        # 再加一阶热惯性（轴承温度不会突变，故障后几秒才缓慢爬升——更真实）
        rng = np.random.default_rng(int(now))
        target = 42.0 + 8.0 * device.load_ratio \
            + 30.0 * min(max((rms - 0.42) / 0.5, 0.0) ** 1.5, 1.17) \
            + rng.standard_normal() * 0.5
        prev = self._temps.get(device.id, target)
        temp = prev + 0.15 * (target - prev)          # 一阶热惯性 α=0.15
        self._temps[device.id] = temp
        temp = round(max(temp, 25.0), 2)

        row = SensorSample(device_id=device.id, ts=now, rpm=device.rpm,
                           vibration_rms=round(rms, 4),
                           vibration_peak=round(peak, 4),
                           temperature=temp, fault_class=fault_class)
        db.add(row)
        self.last_samples[device.id] = {
            "device_id": device.id, "ts": now, "rpm": device.rpm,
            "rms": round(rms, 4), "peak": round(peak, 4), "temp": temp,
            "fault_class": fault_class,
            "health_state": device.health_state,
        }

        # 异常检测（每设备独立基线）
        monitor = self._get_or_create_monitor(device.id)
        events = monitor.check(rms, temp)
        for ev in events:
            self._raise_alarm(db, device.id, ev)

        # 滚动清理：超出上限删除最旧记录
        cnt = db.query(SensorSample).filter_by(device_id=device.id).count()
        if cnt > MAX_ROWS_PER_DEVICE:
            oldest_id = (db.query(SensorSample.id).filter_by(device_id=device.id)
                         .order_by(SensorSample.id.asc()).first()[0])
            db.query(SensorSample).filter(
                SensorSample.device_id == device.id,
                SensorSample.id <= oldest_id).delete(synchronize_session=False)

    def _raise_alarm(self, db, device_id: int, ev: dict):
        """写入预警（同设备同类型未处理预警去重，避免刷屏）"""
        exists = (db.query(Alarm).filter_by(device_id=device_id, alarm_type=ev["type"],
                                            status="active").first())
        if exists:
            return
        db.add(Alarm(device_id=device_id, alarm_type=ev["type"],
                     level=ev["level"], message=ev["message"], value=ev["value"]))

    def log_state_change(self, device_id: int, fault_class: int):
        """故障注入/恢复时的状态变化预警（演示用，与采样去重通道独立）"""
        labels = {0: "恢复正常", 1: "注入内圈故障", 2: "注入外圈故障", 3: "注入滚动体故障"}
        db = SessionLocal()
        try:
            db.add(Alarm(device_id=device_id, alarm_type="状态变化", level=3 if fault_class else 1,
                         message=f"设备状态变化：{labels.get(fault_class, fault_class)}",
                         value=float(fault_class)))
            db.commit()
        finally:
            db.close()


# 全局单例
stream_engine = StreamEngine()
