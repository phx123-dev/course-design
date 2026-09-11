# -*- coding: utf-8 -*-
"""
训练数据集生成 —— 4 类健康状态的模拟振动信号
==============================================
每类生成若干 0.25s 窗口（12000Hz → 3000 点/窗口），写入 data/processed/signal_dataset.csv
（第 1 列为类别标签 0-3，其余 3000 列为振动幅值序列）。

参数随机化（转速 ±2%、噪声 ±30%、相位随机）用于增强样本多样性，
全部由固定 seed 驱动，多次运行结果完全一致（可复现）。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 使 app 包可导入

from app.config import DATASET_CSV
from app.services.signal_gen import CLASS_NAMES, synth_window

SAMPLES_PER_CLASS = 150   # 每类样本数（4 类 × 150 = 600 条）
POINTS = 3000             # 0.25s @ 12000Hz


def generate(n_per_class: int = SAMPLES_PER_CLASS, seed: int = 42) -> np.ndarray:
    """生成数据集矩阵，形状 (n_per_class*4, 1+POINTS)，第 0 列为标签"""
    rng = np.random.default_rng(seed)
    rows = []
    for cls in range(4):
        for i in range(n_per_class):
            # 随机工况抖动：转速 1750±2%，噪声 0.10±30%，独立相位
            rpm = 1750.0 * (1 + rng.uniform(-0.02, 0.02))
            noise = 0.10 * (1 + rng.uniform(-0.3, 0.3))
            sig = synth_window(cls, duration=0.25, rpm=rpm,
                               noise_std=noise, seed=seed * 10000 + cls * 1000 + i)
            rows.append(np.concatenate([[cls], sig]))
    return np.vstack(rows)


def main():
    data = generate()
    DATASET_CSV.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(DATASET_CSV, data, delimiter=",", fmt="%.6f",
               header=",".join(["label"] + [f"v{i}" for i in range(POINTS)]),
               comments="")
    print(f"数据集已生成: {DATASET_CSV}  形状={data.shape}")
    for cls in range(4):
        print(f"  类别 {cls} ({CLASS_NAMES[cls]}) : {n_per_class} 条")


if __name__ == "__main__":
    main()
