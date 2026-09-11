# -*- coding: utf-8 -*-
"""特征工程测试：维度、数值有效性、类间可分性"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.ml.features import FEATURE_NAMES, extract_features, features_to_dict
from app.services.signal_gen import synth_window


class TestFeatures(unittest.TestCase):

    def test_dimension(self):
        """特征向量为 14 维且与特征名一一对应"""
        sig = synth_window(1, seed=0)
        vec = extract_features(sig, 12000, 1750.0)
        self.assertEqual(vec.shape, (14,))
        self.assertEqual(len(FEATURE_NAMES), 14)
        d = features_to_dict(vec)
        self.assertEqual(set(d.keys()), set(FEATURE_NAMES))

    def test_finite(self):
        """任意类别信号的特征均无 NaN/Inf"""
        for cls in range(4):
            sig = synth_window(cls, seed=0)
            vec = extract_features(sig, 12000, 1750.0)
            self.assertTrue(np.isfinite(vec).all(), f"cls={cls} 特征含 NaN/Inf")

    def test_class_separability(self):
        """四类信号特征均值存在显著差异（为分类模型提供依据）"""
        means = {}
        for cls in range(4):
            vecs = [extract_features(synth_window(cls, seed=i), 12000, 1750.0)
                    for i in range(20)]
            means[cls] = np.mean(vecs, axis=0)
        # 三类故障的波峰因子/峭度应显著高于正常
        normal_kurt = means[0][FEATURE_NAMES.index("kurtosis")]
        for cls in (1, 2, 3):
            self.assertGreater(means[cls][FEATURE_NAMES.index("kurtosis")],
                               normal_kurt + 1.0, f"cls={cls} 峭度区分不足")


if __name__ == "__main__":
    unittest.main()
