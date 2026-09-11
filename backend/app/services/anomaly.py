# -*- coding: utf-8 -*-
"""
异常检测 —— 3σ 阈值 + 孤立森林 + 温度超限
==========================================
1) 3σ 阈值（统计学方法）：
   正常工况下振动 RMS 近似高斯分布，若实时值超出 μ+3σ
   （偏离均值 3 个标准差，出现概率 <0.3%）判定为异常。
2) 孤立森林（IsolationForest，sklearn）：
   无监督模型，通过随机切分特征空间度量"孤立程度"，
   异常点更易被隔离（路径更短），分数 <0 判定为异常。
3) 温度超限：轴承温度超过阈值（默认 70℃）判定异常。

流引擎对每台设备维护独立检测器：基线由正常工况信号统计得到。
"""
import numpy as np
from sklearn.ensemble import IsolationForest


class SigmaDetector:
    """3σ 阈值检测器（单特征：振动 RMS）"""

    def __init__(self, baseline: list):
        self.mean = float(np.mean(baseline))
        self.std = float(np.std(baseline))
        self.threshold = self.mean + 3.0 * self.std

    def is_anomaly(self, value: float) -> tuple:
        """返回 (是否异常, 偏离倍数)"""
        if self.std < 1e-12:
            return False, 0.0
        ratio = (value - self.mean) / self.std
        return value > self.threshold, ratio


class IsoForestDetector:
    """孤立森林检测器（特征：RMS + 温度，训练集为正常工况样本）"""

    def __init__(self, samples: list, contamination: float = 0.05, random_state: int = 42):
        X = np.array(samples)
        self.model = IsolationForest(contamination=contamination,
                                     random_state=random_state, n_estimators=100)
        self.model.fit(X)

    def is_anomaly(self, rms: float, temp: float) -> bool:
        # 返回 -1 表示异常（分数为负）
        return self.model.predict([[rms, temp]])[0] == -1


class TemperatureChecker:
    """温度超限检测"""

    def __init__(self, limit: float = 70.0):
        self.limit = limit

    def is_over(self, temp: float) -> bool:
        return temp > self.limit


class DeviceAnomalyMonitor:
    """单设备异常监测器：组合 3σ + 孤立森林 + 温度超限，输出预警事件列表"""

    def __init__(self, rms_baseline: list, iso_samples: list, temp_limit: float = 70.0):
        self.sigma = SigmaDetector(rms_baseline)
        self.iso = IsoForestDetector(iso_samples) if len(iso_samples) >= 20 else None
        self.temp = TemperatureChecker(temp_limit)

    def check(self, rms: float, temp: float) -> list:
        """返回触发的预警事件：[{type, level, message, value}]"""
        events = []
        is_anomaly, ratio = self.sigma.is_anomaly(rms)
        if is_anomaly:
            events.append({
                "type": "3σ异常", "level": 2,
                "message": f"振动 RMS 超出正常基线 {ratio:.1f}σ",
                "value": round(rms, 4),
            })
        if self.iso and self.iso.is_anomaly(rms, temp):
            events.append({
                "type": "隔离森林", "level": 3,
                "message": "孤立森林判定 (RMS,温度) 特征为异常点",
                "value": round(rms, 4),
            })
        if self.temp.is_over(temp):
            events.append({
                "type": "温度超限", "level": 3,
                "message": f"轴承温度 {temp:.1f}℃ 超过阈值 {self.temp.limit:.0f}℃",
                "value": round(temp, 2),
            })
        return events
