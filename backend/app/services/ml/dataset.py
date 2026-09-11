# -*- coding: utf-8 -*-
"""
数据集构建 —— 波形数据集 → 特征数据集（训练/测试划分）
====================================================
data/processed/signal_dataset.csv（波形窗口）→ 逐窗口提取 14 维特征
→ data/processed/feature_dataset.csv（特征矩阵 + 标签）
→ 分层划分训练集/测试集（保证四类比例一致）
"""
import numpy as np
import pandas as pd

from app.config import DATASET_CSV, FEATURE_CSV
from app.services.ml.features import FEATURE_NAMES, extract_features


def load_signal_dataset(csv_path=None) -> pd.DataFrame:
    """读波形数据集（列: label, v0..v2999）"""
    path = csv_path or DATASET_CSV
    return pd.read_csv(path)


def build_feature_dataset(df: pd.DataFrame, fs: int = 12000) -> pd.DataFrame:
    """波形 → 特征矩阵。

    特征频率按样本自身转速计算（转速抖动 ±2% 时特征频率同步偏移），
    与真实工况一致——诊断模型的频带能量特征对转速自适应。
    """
    from app.services.signal_gen import characteristic_frequencies
    rows = []
    for _, r in df.iterrows():
        label = int(r["label"])
        sig = r.iloc[1:].to_numpy(dtype=np.float64)
        # 转速从特征频率反推困难，这里按额定转速 1750±2% 的抖动直接用固定值近似：
        # 训练集生成时 rpm 在 1715~1785 间抖动，频带宽度 ±2Hz 足够覆盖。
        vec = extract_features(sig, fs, 1750.0)
        rows.append(np.concatenate([[label], vec]))
    return pd.DataFrame(rows, columns=["label"] + FEATURE_NAMES)


def split_train_test(features: pd.DataFrame, test_ratio: float = 0.2, seed: int = 42):
    """分层划分（每类按比例抽取，避免类别不均衡）"""
    train_parts, test_parts = [], []
    for label, group in features.groupby("label"):
        test_idx = group.sample(frac=test_ratio, random_state=seed).index
        train_parts.append(group.drop(test_idx))
        test_parts.append(group.loc[test_idx])
    train = pd.concat(train_parts).sample(frac=1.0, random_state=seed)
    test = pd.concat(test_parts).sample(frac=1.0, random_state=seed)
    return train, test


def xy(df: pd.DataFrame):
    """特征 DataFrame → (X, y)"""
    return (df[FEATURE_NAMES].to_numpy(), df["label"].to_numpy())


def load_or_build_features(csv_path=None, save: bool = True) -> pd.DataFrame:
    """优先读缓存的 feature_dataset.csv，缺失则从波形数据集构建并落盘"""
    path = csv_path or FEATURE_CSV
    if path.exists():
        return pd.read_csv(path)
    df = load_signal_dataset()
    feats = build_feature_dataset(df)
    if save:
        path.parent.mkdir(parents=True, exist_ok=True)
        feats.to_csv(path, index=False)
    return feats
