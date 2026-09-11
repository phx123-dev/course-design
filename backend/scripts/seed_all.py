# -*- coding: utf-8 -*-
"""
一键初始化：数据库 → 基础种子（账号/设备台账） → 训练数据集 → （可选）模型训练 → （可选）知识库入库
======================================================================================
用法：
  py -3.13 scripts/seed_all.py                # 全量：数据集 + 全量训练 + 知识库入库
  py -3.13 scripts/seed_all.py --quick        # 快速：小样本快速训练（新环境 1 分钟内可演示）
  py -3.13 scripts/seed_all.py --no-train --no-knowledge   # 仅建库与数据集
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATASET_CSV
from app.db import init_db, seed_basic, SessionLocal

QUICK_SAMPLES = 80     # 快速训练每类样本数
FULL_SAMPLES = 150


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="快速训练（小样本）")
    parser.add_argument("--no-train", action="store_true")
    parser.add_argument("--no-knowledge", action="store_true")
    args = parser.parse_args()

    print("== [1/4] 建表与基础种子 ==")
    init_db()
    db = SessionLocal()
    try:
        seed_basic(db)
    finally:
        db.close()
    print("   账号: admin/engineer/manager (密码 123456)；设备台账 6 台")

    print("== [2/4] 生成训练数据集 ==")
    from scripts.generate_signals import generate
    if not DATASET_CSV.exists():
        data = generate(FULL_SAMPLES)
        import numpy as np
        DATASET_CSV.parent.mkdir(parents=True, exist_ok=True)
        np.savetxt(DATASET_CSV, data, delimiter=",", fmt="%.6f",
                   header=",".join(["label"] + [f"v{i}" for i in range(data.shape[1] - 1)]),
                   comments="")
    print(f"   数据集: {DATASET_CSV}")

    if not args.no_train:
        print("== [3/4] 训练故障分类模型 ==")
        from app.services.ml.train import train_and_save
        result = train_and_save(n_per_class=QUICK_SAMPLES if args.quick else None)
        print(f"   最优模型 {result['best_model']} 准确率={result['accuracy']:.4f}")

    if not args.no_knowledge:
        print("== [4/4] 知识库语料入库 ==")
        from scripts.ingest_knowledge import ingest_all
        n = ingest_all()
        print(f"   入库 {n} 篇语料")
    else:
        print("== [4/4] 跳过知识库入库（--no-knowledge） ==")

    print("初始化完成。运行 start.bat 启动系统。")


if __name__ == "__main__":
    main()
