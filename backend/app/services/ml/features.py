# -*- coding: utf-8 -*-
"""
特征工程 —— 振动信号时域 + 频域统计特征提取
============================================
时域特征（描述信号能量与冲击特性）：
  均值 μ = (1/N)Σxᵢ              均方根 RMS = sqrt((1/N)Σxᵢ²)
  峰值 x_peak = max|xᵢ|          峰峰值 x_pp = max - min
  波峰因子 CF = x_peak / RMS       （冲击型故障会显著增大）
  峭度 K = (1/N)Σ(xᵢ-μ)⁴ / σ⁴      （对早期冲击故障敏感，正常≈3）
  偏度 S = (1/N)Σ(xᵢ-μ)³ / σ³      （信号分布不对称度）
  方差 σ²、标准差 σ

频域特征（基于 FFT，描述故障特征频率能量）：
  - 频谱主频（能量最大处频率）与主频幅值
  - BPFI/BPFO/BSF 特征频率及其 2 倍频处的频带能量（各取 ±2Hz 窄带求和）
  - 谱质心（频谱重心，表征能量向高频迁移）

特征向量共 14 维，由 dataset.py 生成训练集 CSV，train.py 训练分类模型。
"""
import numpy as np

# 特征名清单（保持与生成顺序一致，供报告与前端展示使用）
FEATURE_NAMES = [
    "mean", "std", "rms", "peak", "peak2peak", "crest_factor",
    "kurtosis", "skewness", "variance",
    "dominant_freq", "dominant_amp",
    "bpfi_band", "bpfo_band", "bsf_band",
]


def time_domain_features(x: np.ndarray) -> dict:
    """时域 9 维特征"""
    mu = float(np.mean(x))
    sigma = float(np.std(x))
    rms = float(np.sqrt(np.mean(np.square(x))))
    peak = float(np.max(np.abs(x)))
    pp = float(np.max(x) - np.min(x))
    # 波峰因子：峰/均方根（正常信号约 3~5，冲击型故障可达 10 以上）
    cf = peak / rms if rms > 1e-12 else 0.0
    # 峭度：四阶中心矩/标准差的四次方（正常信号接近 3）
    kurt = float(np.mean((x - mu) ** 4) / (sigma ** 4 + 1e-12))
    # 偏度：三阶中心矩/标准差的三次方
    skew = float(np.mean((x - mu) ** 3) / (sigma ** 3 + 1e-12))
    return {
        "mean": mu, "std": sigma, "rms": rms, "peak": peak, "peak2peak": pp,
        "crest_factor": cf, "kurtosis": kurt, "skewness": skew,
        "variance": float(np.var(x)),
    }


def frequency_features(x: np.ndarray, fs: int, bpfi: float, bpfo: float, bsf: float) -> dict:
    """频域 5 维特征。

    FFT 后取单边谱幅值；特征频带能量 = 特征频率 ±2Hz 内谱线平方和
    （窄带能量大说明该故障特征频率处存在周期性冲击）。
    """
    n = len(x)
    window = np.hanning(n)                              # 汉宁窗抑制频谱泄漏
    spectrum = np.fft.rfft(x * window)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    mag = np.abs(spectrum)

    # 主频：幅值最大谱线对应的频率（排除直流分量 0Hz）
    mag_no_dc = mag.copy()
    mag_no_dc[0] = 0.0
    dom_idx = int(np.argmax(mag_no_dc))
    dominant_freq = float(freqs[dom_idx])
    dominant_amp = float(mag[dom_idx])

    def band_energy(fc: float, half_width: float = 2.0) -> float:
        """特征频率 fc ± half_width 内的能量（谱线幅值平方和）"""
        mask = (freqs >= fc - half_width) & (freqs <= fc + half_width)
        return float(np.sum(mag[mask] ** 2))

    return {
        "dominant_freq": dominant_freq,
        "dominant_amp": dominant_amp,
        "bpfi_band": band_energy(bpfi),
        "bpfo_band": band_energy(bpfo),
        "bsf_band": band_energy(bsf),
    }


def extract_features(x: np.ndarray, fs: int, rpm: float,
                     bpfi: float = None, bpfo: float = None, bsf: float = None) -> np.ndarray:
    """提取完整 14 维特征向量（np.ndarray，与 FEATURE_NAMES 顺序一致）。

    若未显式给出特征频率，按轴承几何参数自动计算。
    """
    from app.services.signal_gen import characteristic_frequencies
    if bpfi is None:
        cf = characteristic_frequencies(rpm)
        bpfi, bpfo, bsf = cf["bpfi"], cf["bpfo"], cf["bsf"]

    feats = {}
    feats.update(time_domain_features(x))
    feats.update(frequency_features(x, fs, bpfi, bpfo, bsf))
    return np.array([feats[name] for name in FEATURE_NAMES], dtype=np.float64)


def features_to_dict(vec: np.ndarray) -> dict:
    """特征向量 → 字典（接口返回/前端展示用）"""
    return {name: float(v) for name, v in zip(FEATURE_NAMES, vec)}
