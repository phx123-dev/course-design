# -*- coding: utf-8 -*-
"""异常检测测试：3σ 阈值 / 温度超限 / 孤立森林（RUL 测试在 M6 补充）"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.anomaly import (DeviceAnomalyMonitor, SigmaDetector,
                                  TemperatureChecker)
from app.services.signal_gen import stream_window


def _rms(sig):
    return float(np.sqrt(np.mean(np.square(sig))))


class TestAnomaly(unittest.TestCase):

    def test_sigma_normal_no_alarm(self):
        """正常值不应触发 3σ"""
        baseline = [0.30 + 0.02 * np.sin(i) for i in range(40)]
        det = SigmaDetector(baseline)
        self.assertFalse(det.is_anomaly(0.31)[0])

    def test_sigma_outlier_alarm(self):
        """超 3σ 的冲击值应触发"""
        baseline = [0.30 + 0.01 * i for i in range(40)]
        det = SigmaDetector(baseline)
        is_anomaly, ratio = det.is_anomaly(1.5)
        self.assertTrue(is_anomaly)
        self.assertGreater(ratio, 3.0)

    def test_temperature_limit(self):
        ck = TemperatureChecker(70.0)
        self.assertFalse(ck.is_over(65.0))
        self.assertTrue(ck.is_over(75.0))

    def test_monitor_detects_fault_injection(self):
        """端到端：正常基线 vs 故障信号，组合监测器应产出预警事件"""
        base_rms = [_rms(stream_window(1, 0, ts=1e9 + i)) for i in range(40)]
        iso = [[r, 45.0] for r in base_rms]
        mon = DeviceAnomalyMonitor(base_rms, iso)
        fault_rms = _rms(stream_window(1, 1, ts=2e9))
        events = mon.check(fault_rms, 48.0)
        types = {e["type"] for e in events}
        self.assertIn("3σ异常", types, f"故障 RMS={fault_rms} 应触发 3σ，基线均值={np.mean(base_rms):.3f}")
        # 高温场景：3σ 不触发时温度超限也应触发
        ev2 = mon.check(base_rms[0], 85.0)
        self.assertTrue(any(e["type"] == "温度超限" for e in ev2))


if __name__ == "__main__":
    unittest.main()
