# -*- coding: utf-8 -*-
"""
信号合成模块 —— 确定性轴承振动信号生成器
=========================================
作用：
  1) 生成机器学习训练集（4 类故障/健康状态的可区分振动样本）；
  2) 生成实时监控数据流（设备按当前健康状态连续出数）；
  3) 波形确定性回放（同一设备同一时刻总能生成完全相同的波形，波形不入库）。

物理模型（滚动轴承故障机理，参考 Randall 等轴承诊断文献）：
  滚动轴承由内圈、外圈、滚动体、保持架组成。当某个元件表面出现局部缺陷
  （点蚀、剥落）时，滚动体每经过一次缺陷位置就产生一次冲击脉冲，
  冲击重复频率即"故障特征频率"，由转速与轴承几何参数决定：

    fr   = rpm / 60                          # 转频（轴旋转频率）
    BPFI = fr * n/2 * (1 + d/D * cosφ)       # 内圈故障特征频率
    BPFO = fr * n/2 * (1 - d/D * cosφ)       # 外圈故障特征频率
    BSF  = fr * D/(2d) * (1 - (d/D*cosφ)^2)  # 滚动体故障特征频率
    其中 n=滚珠数, d=滚珠直径, D=节圆直径, φ=接触角

  信号合成：正常信号 = 转频基波 + 谐波 + 高斯白噪声；
  故障信号 = 正常信号 + 故障特征频率上的周期性指数衰减冲击串：
    x_imp(t) = Σ_k A_k · e^{-β(t-kT)} · sin(2π f_n (t-kT)),  t-kT ∈ [0, τ]
  其中 T = 1/f_fault 为冲击周期，f_n 为系统固有频率，β 为衰减系数。
  内圈故障的冲击幅值 A_k 还受到转频调制（缺陷随内圈旋转周期性进出承载区），
  频谱上表现为 BPFI 两侧出现 fr 边带——与真实数据特征一致。

设计要点：
  - 全部随机量由 seed 控制，保证结果可复现（答辩/复现实验一致）；
  - 各类信号在时域统计量（RMS/峭度）与频域特征频带能量上均有显著差异，
    足以支撑分类模型训练到 90% 以上准确率。
"""

import hashlib
import numpy as np

# 滚动轴承几何参数（深沟球轴承 6205 量级，与 CWRU 公开数据集接近）
BEARING_PARAMS = {
    "n_balls": 9,        # 滚珠数 n
    "pitch_d": 39.0,     # 节圆直径 D (mm)
    "ball_d": 7.94,      # 滚珠直径 d (mm)
    "contact_angle": 0.0,  # 接触角 φ（弧度）
}

# 故障/健康类别标签（与数据库 equipment.health_state、ML 模型标签一一对应）
FAULT_CLASSES = {
    "normal": 0,   # 正常
    "inner": 1,    # 内圈故障
    "outer": 2,    # 外圈故障
    "ball": 3,     # 滚动体故障
}
CLASS_NAMES = {v: k for k, v in FAULT_CLASSES.items()}
CLASS_LABELS_ZH = {0: "正常", 1: "内圈故障", 2: "外圈故障", 3: "滚动体故障"}

FS = 12000  # 采样率 Hz（与 CWRU 12kHz 档一致）


def characteristic_frequencies(rpm: float, bearing: dict = None) -> dict:
    """按几何公式计算各故障特征频率。返回 {'fr','bpfi','bpfo','bsf',...}"""
    b = bearing or BEARING_PARAMS
    n, D, d, phi = b["n_balls"], b["pitch_d"], b["ball_d"], b["contact_angle"]
    fr = rpm / 60.0
    ratio = d / D * np.cos(phi)
    return {
        "fr": fr,
        "bpfi": fr * n / 2 * (1 + ratio),          # 内圈特征频率
        "bpfo": fr * n / 2 * (1 - ratio),          # 外圈特征频率
        "bsf": fr * D / (2 * d) * (1 - ratio ** 2),  # 滚动体特征频率
    }


def _impulse_train(fault_class: int, t: np.ndarray, fr: float, bearing: dict,
                   amplitude: float, fn: float = 3200.0, beta: float = 900.0) -> np.ndarray:
    """构造故障冲击串。

    对每一故障特征周期 T 内的冲击：
      冲击 = A_k * exp(-beta*(t-tk)) * sin(2*pi*fn*(t-tk))
    内圈故障 A_k 随转频调制：A_k = amplitude * (0.6 + 0.4*cos(2*pi*fr*tk))
    其他类型 A_k 为常数（外圈缺陷位置固定，无调制）。
    """
    freqs = characteristic_frequencies(fr * 60.0, bearing)  # 由转频反推转速再算特征频率
    f_fault = {
        1: freqs["bpfi"],
        2: freqs["bpfo"],
        3: freqs["bsf"],
    }[fault_class]

    sig = np.zeros_like(t)
    T = 1.0 / f_fault                       # 冲击周期
    for tk in np.arange(0, t[-1] - 1e-9, T):
        idx = np.nonzero(t >= tk)[0]
        idx = idx[t[idx] - tk <= 6.0 / beta]  # 冲击有效持续时间（衰减包络截断）
        if idx.size == 0:
            continue
        tau = t[idx] - tk
        if fault_class == 1:                # 内圈故障：转频幅度调制
            Ak = amplitude * (0.6 + 0.4 * np.cos(2 * np.pi * fr * tk))
        else:
            Ak = amplitude
        # 注意：必须用索引数组累加（sig[mask][...] += 会写入副本，静默失效）
        sig[idx] += Ak * np.exp(-beta * tau) * np.sin(2 * np.pi * fn * tau)
    return sig


def synth_window(fault_class: int, fs: int = FS, duration: float = 0.25,
                 rpm: float = 1750.0, noise_std: float = 0.10,
                 amplitude: float = 5.0, seed: int = None,
                 bearing: dict = None, degrade: float = 0.0) -> np.ndarray:
    """合成一段振动信号。

    参数：
      fault_class : 0 正常 / 1 内圈 / 2 外圈 / 3 滚动体
      duration    : 时长（秒），训练样本 0.25s（3000 点）
      rpm         : 转速（用于转频与特征频率计算，训练时轻微抖动以增加多样性）
      noise_std   : 白噪声标准差
      amplitude   : 故障冲击幅值（真实轴承缺陷冲击为短时高强度脉冲，
                    幅值远大于正常振动分量，此处取 5.0）
      degrade     : 故障严重度 [0,1]，控制冲击幅值（退化序列使用）
    """
    rng = np.random.default_rng(seed)
    b = bearing or BEARING_PARAMS
    t = np.arange(0, duration, 1.0 / fs)
    fr = rpm / 60.0

    # 正常分量：转频基波 + 2/3 次谐波（不平衡/不对中造成的常见振动成分）
    base = (0.5 * np.sin(2 * np.pi * fr * t)
            + 0.15 * np.sin(2 * np.pi * 2 * fr * t)
            + 0.06 * np.sin(2 * np.pi * 3 * fr * t))

    if fault_class == 0:
        sig = base
    else:
        # 故障冲击串，严重度影响冲击幅值；正常分量按 0.15 比例保留
        # （故障轴承的振动以冲击成分为主，周期性正弦成分被削弱）
        amp = amplitude * (0.4 + 0.6 * max(degrade, 0.05))
        sig = 0.15 * base + _impulse_train(fault_class, t, fr, b, amp)

    # 加性高斯白噪声（传感器本底噪声）
    sig = sig + noise_std * rng.standard_normal(len(t))
    return sig


def synth_degradation_series(fault_class: int, n_steps: int = 120,
                             fs: int = FS, duration: float = 0.25,
                             rpm: float = 1750.0, seed: int = 0) -> list:
    """生成一条"全寿命退化"序列（模拟 NASA 轴承退化数据形态）。

    故障严重度从 0 线性增长到 1（早期轻微损伤 → 末期严重失效），
    每步返回该时刻的振动窗口，供 RUL 估计与退化趋势演示使用。
    """
    return [
        synth_window(fault_class, fs, duration, rpm,
                     seed=seed + i, degrade=i / max(n_steps - 1, 1))
        for i in range(n_steps)
    ]


def _seed_of(device_id: int, ts: float) -> int:
    """设备+时间戳 → 确定性种子（波形回放：同一时刻永远生成相同波形）。"""
    h = hashlib.md5(f"{device_id}:{int(ts * 10)}".encode()).hexdigest()
    return int(h[:8], 16)


def stream_window(device_id: int, fault_class: int, ts: float,
                  rpm: float = 1750.0, degrade: float = 0.8,
                  fs: int = FS, duration: float = 0.25) -> np.ndarray:
    """实时流波形：由 (设备, 时间) 决定种子，确定性生成、可复现回放。"""
    return synth_window(fault_class, fs, duration, rpm,
                        seed=_seed_of(device_id, ts), degrade=degrade)
