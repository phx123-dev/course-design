# -*- coding: utf-8 -*-
"""全局配置：路径 + 大模型参数（.env 环境变量，服务端保存，前端不可见）"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings

# backend/app/config.py -> backend -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data" / "processed"     # 生成数据/模型（不入 git）
DB_PATH = DATA_DIR / "phx.db"                      # SQLite 数据库
MODEL_DIR = DATA_DIR / "models"                    # ML 模型 .pkl
DATASET_CSV = DATA_DIR / "signal_dataset.csv"      # 训练波形数据集
FEATURE_CSV = DATA_DIR / "feature_dataset.csv"     # 特征数据集
EVAL_REPORT = DATA_DIR / "eval_report.json"        # 模型评测报告
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"         # 知识库语料
FRONTEND_DIR = PROJECT_ROOT / "frontend"           # 前端静态资源


class Settings(BaseSettings):
    """服务端配置。.env 文件位于项目根目录，含 API Key，严禁提交 git。"""

    deepseek_api_key: str = ""            # 为空时智能层自动进入离线模拟模式
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    llm_timeout: float = 30.0             # 单次 LLM 调用超时（秒）

    # 诊断响应性能指标（任务书：单次问答/诊断 ≤ 10s，此处留余量）
    diagnose_timeout: float = 9.0

    class Config:
        env_file = str(PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# 确保运行时目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
