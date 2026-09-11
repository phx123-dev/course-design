# -*- coding: utf-8 -*-
"""ML 流水线测试：快速训练 → 准确率验收 → 预测服务 → RUL 合理性"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import EVAL_REPORT
from app.db import SessionLocal, init_db
from app.services.ml.dataset import load_or_build_features, split_train_test, xy
from app.services.ml.rul import calibrate_rms_bounds, estimate_rul, health_index
from app.services.ml.train import train_and_save
from app.services.signal_gen import synth_window


class TestMLPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        # 快速训练（每类 60 样本），约 10-20 秒
        cls.result = train_and_save(quick=True, n_per_class=60)

    def test_accuracy_meets_target(self):
        """验收：测试集准确率 ≥ 0.90（任务书技术目标）"""
        self.assertGreaterEqual(self.result["accuracy"], 0.90,
                                f"准确率 {self.result['accuracy']:.4f} 未达 0.90 验收线")

    def test_eval_report_written(self):
        import json
        report = json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["accuracy"], self.result["accuracy"])
        self.assertIn("report", report)

    def test_feature_dataset_cache(self):
        """特征缓存可复用且四类齐全"""
        feats = load_or_build_features()
        self.assertEqual(set(feats["label"].unique()), {0, 1, 2, 3})

    def test_predict_service(self):
        """预测服务：四类概率和为 1，故障窗口被正确分类"""
        from app.services.ml.predict import predict_health
        db = SessionLocal()
        try:
            for cls, name in [(0, "正常"), (1, "内圈故障"), (2, "外圈故障"), (3, "滚动体故障")]:
                win = synth_window(cls, seed=99)
                res = predict_health(db, 1, win, 1750.0, save=False)
                self.assertTrue(res["available"])
                self.assertAlmostEqual(
                    res["prob_normal"] + res["prob_inner"] + res["prob_outer"] + res["prob_ball"],
                    1.0, places=3)
                if cls != 0:
                    self.assertEqual(res["pred_label"], name, f"类别 {cls} 预测错误")
        finally:
            db.close()

    def test_rul_bounds_and_index(self):
        """RUL：标定区间单调、健康指标单调递减"""
        rms_n, rms_f = calibrate_rms_bounds(2, device_id=0)
        self.assertGreater(rms_f, rms_n)
        hi_start = health_index(rms_n, rms_n, rms_f)
        hi_end = health_index(rms_f, rms_n, rms_f)
        self.assertAlmostEqual(hi_start, 1.0, places=2)
        self.assertLess(hi_end, 0.05)

    def test_rul_degradation_extrapolation(self):
        """RUL 外推：构造 48 小时退化历史（每小时一条），应检测到退化并给出小时数"""
        db = SessionLocal()
        try:
            from app.db import SensorSample
            from app.services.signal_gen import synth_degradation_series
            import time
            # 48 步退化序列（模拟 48 小时全寿命），写入模拟历史（设备 999，外圈故障）
            series = synth_degradation_series(2, n_steps=48, seed=5)
            base = time.time() - 47 * 3600
            for i, s in enumerate(series):
                db.add(SensorSample(device_id=999, ts=base + i * 3600,
                                    rpm=1750, vibration_rms=float(np.sqrt(np.mean(s**2))),
                                    vibration_peak=0, temperature=50, fault_class=2))
            db.commit()
            # "当前"取全寿命 3/4 处（HI≈0.25，未失效）→ 应外推出约 4 小时
            rms_now = float(np.sqrt(np.mean(series[36] ** 2)))
            res = estimate_rul(db, 999, 2, rms_now)
            self.assertTrue(res["degrading"], "退化趋势应被检测到")
            self.assertIsNotNone(res["rul_hours"])
            self.assertGreater(res["rul_hours"], 1.0)
            self.assertLess(res["rul_hours"], 47.0)
            # 清理测试数据
            db.query(SensorSample).filter(SensorSample.device_id == 999).delete()
            db.commit()
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
