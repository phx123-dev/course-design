# -*- coding: utf-8 -*-
"""模型训练 CLI：
  py -3.13 scripts/train_models.py           # 全量训练（300 棵树级别）
  py -3.13 scripts/train_models.py --quick   # 快速训练（演示兜底，1 分钟内）
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import init_db
from app.services.ml.train import train_and_save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="快速训练（小参数）")
    args = parser.parse_args()
    init_db()
    result = train_and_save(quick=args.quick)
    print(f"\n完成: {result['best_model']} 测试集准确率 = {result['accuracy']:.4f}")
    if result["accuracy"] < 0.90:
        print("[警告] 准确率低于 0.90 验收线，请检查数据生成参数")
        sys.exit(1)


if __name__ == "__main__":
    main()
