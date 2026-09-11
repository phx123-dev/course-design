# -*- coding: utf-8 -*-
"""信号合成模块测试：可复现性 + 四类信号可区分性"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.signal_gen import (CLASS_NAMES, characteristic_frequencies,
                                     stream_window, synth_window)


class TestSignalGen(unittest.TestCase):

    def test_reproducible(self):
        """同一 seed 生成完全相同的信号（可复现性）"""
        a = synth_window(1, seed=7)
        b = synth_window(1, seed=7)
        np.testing.assert_array_equal(a, b)
        c = synth_window(1, seed=8)
        self.assertFalse(np.array_equal(a, c))

    def test_shape_and_finite(self):
        """信号长度正确且无 NaN/Inf"""
        sig = synth_window(2, duration=0.25)
        self.assertEqual(len(sig), 3000)
        self.assertTrue(np.isfinite(sig).all())

    def test_characteristic_frequencies(self):
        """特征频率物理公式：BPFI > BPFO > BSF 且均为正数"""
        cf = characteristic_frequencies(1750.0)
        self.assertGreater(cf["bpfi"], cf["bpfo"] > 0)
        self.assertGreater(cf["bpfo"], cf["bsf"] > 0)
        self.assertAlmostEqual(cf["fr"], 1750 / 60, places=3)

    def test_fault_impulse_indicators(self):
        """故障信号冲击性指标（峰值/波峰因子）应显著高于正常信号。

        注：早期轴承故障的 RMS 变化不明显，判别靠冲击性指标（峭度/波峰因子/峰值），
        这与真实轴承故障特征一致（CWRU 数据同此规律）。
        """
        peak, crest = [], []
        for cls in range(4):
            sig = synth_window(cls, seed=0, noise_std=0.05)
            rms = np.sqrt(np.mean(sig ** 2))
            peak.append(np.max(np.abs(sig)))
            crest.append(np.max(np.abs(sig)) / rms)
        self.assertGreater(min(peak[1:]), peak[0] * 2)       # 故障峰值显著更高
        self.assertGreater(min(crest[1:]), crest[0] * 2)     # 波峰因子显著更高

    def test_fault_kurtosis_impulsive(self):
        """故障信号峭度应显著高于正常信号（冲击性标志）"""
        def kurt(x):
            return np.mean((x - x.mean()) ** 4) / (x.std() ** 4 + 1e-12)
        normal_k = kurt(synth_window(0, seed=1))
        fault_k = kurt(synth_window(1, seed=1))
        self.assertGreater(fault_k, normal_k * 2)

    def test_stream_window_deterministic_replay(self):
        """实时流波形确定性回放：同设备同时刻一致，异时刻不同"""
        a = stream_window(1, 1, ts=1000.0)
        b = stream_window(1, 1, ts=1000.0)
        c = stream_window(1, 1, ts=1000.2)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a, c))


if __name__ == "__main__":
    unittest.main()
