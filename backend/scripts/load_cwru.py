# -*- coding: utf-8 -*-
"""
可选脚本：加载凯斯西储大学（CWRU）轴承数据集（.mat 格式）
==========================================================
说明：本项目默认使用模拟信号生成器（确定性可复现），本脚本仅作为
"接入公开数据集"的可选补充验证，不在关键路径上。

使用方法：
  1) 从 CWRU 官网下载 .mat 数据文件（如 12k Drive End Bearing Fault Data）；
  2) py -3.13 scripts/load_cwru.py <目录或.mat文件> [--out data/processed/cwru_features.csv]
  3) 脚本提取驱动端振动信号窗口并计算 14 维特征，输出特征 CSV 供对比分析。

CWRU 类别标签约定（本脚本映射）：
  0 正常(Normal Baseline) / 1 内圈(IR) / 2 外圈(OR) / 3 滚动体(Ball)
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.io import loadmat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ml.features import FEATURE_NAMES, extract_features

CWRU_CLASS_MAP = {
    "normal": 0, "IR": 1, "OR": 2, "B": 3,      # 文件名字段: 内圈 IR / 外圈 OR / 滚动体 B
}


def load_mat(path: Path, rpm: float = 1750.0, fs: int = 12000,
             window_len: int = 3000, stride: int = 1500) -> list:
    """读取单个 .mat，按滑动窗口切分并提取特征"""
    data = loadmat(str(path))
    # 驱动端振动信号键名为 DE_time（不同文件略有差异，逐键尝试）
    sig = None
    for key in ("DE_time", "X097_DE_time", "X098_DE_time", "X099_DE_time"):
        if key in data:
            sig = data[key].ravel()
            break
    if sig is None:
        raise ValueError(f"{path.name}: 未找到驱动端振动信号键")

    cls = CWRU_CLASS_MAP.get(next((k for k in CWRU_CLASS_MAP if k in path.name), "normal"), 0)
    rows = []
    for start in range(0, len(sig) - window_len, stride):
        win = sig[start:start + window_len]
        vec = extract_features(win, fs, rpm)
        rows.append([cls] + list(vec))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help=".mat 文件或目录")
    parser.add_argument("--out", default="data/processed/cwru_features.csv")
    parser.add_argument("--rpm", type=float, default=1750.0)
    args = parser.parse_args()

    src = Path(args.src)
    files = sorted(src.glob("*.mat")) if src.is_dir() else [src]
    rows = []
    for f in files:
        try:
            rows.extend(load_mat(f, rpm=args.rpm))
            print(f"  ✓ {f.name} -> {len(rows)} 窗口累计")
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")
    if not rows:
        print("未加载到任何数据")
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(out, np.array(rows), delimiter=",", fmt="%.6f",
               header="label," + ",".join(FEATURE_NAMES), comments="")
    print(f"已输出特征 CSV: {out}（{len(rows)} 窗口 × 14 维特征）")
    print("提示：可对比该特征分布与模拟数据集（signal_dataset.csv）的差异；")
    print("如需参与训练，将特征并入 data/processed/feature_dataset.csv 后重跑 train_models.py。")


if __name__ == "__main__":
    main()
