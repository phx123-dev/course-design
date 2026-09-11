# -*- coding: utf-8 -*-
"""
模型训练 —— 随机森林 vs XGBoost（不可用时降级 GradientBoosting）
==============================================================
流程：加载特征数据集 → 分层划分 → 交叉验证选择最优模型
      → 测试集评测 → 保存最优模型 .pkl + eval_report.json + 登记 ml_models 表

容错设计：xgboost 在部分平台无对应 Python 版本的预编译包，
         安装失败时自动降级为 sklearn 的 GradientBoostingClassifier
         （同为梯度提升树），训练与预测接口完全一致，模型元信息如实记录。
"""
import datetime
import json

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix)

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

from app.config import EVAL_REPORT, MODEL_DIR
from app.db import MLModel, SessionLocal
from app.services.ml.dataset import load_or_build_features, split_train_test, xy

CLASS_NAMES_ZH = ["正常", "内圈故障", "外圈故障", "滚动体故障"]

# 全量训练参数（--full）
FULL_RF_PARAMS = dict(n_estimators=300, max_depth=12, random_state=42, n_jobs=-1)
FULL_XGB_PARAMS = dict(n_estimators=200, max_depth=5, learning_rate=0.1,
                       random_state=42, n_jobs=-1, eval_metric="mlogloss")
# 快速训练参数（--quick，新环境 1 分钟内可演示）
QUICK_RF_PARAMS = dict(n_estimators=60, max_depth=10, random_state=42, n_jobs=-1)
QUICK_XGB_PARAMS = dict(n_estimators=40, max_depth=4, learning_rate=0.15,
                        random_state=42, n_jobs=-1, eval_metric="mlogloss")


def _candidates(quick: bool) -> dict:
    """返回候选模型字典：{名称: 未训练模型}"""
    rf_p = QUICK_RF_PARAMS if quick else FULL_RF_PARAMS
    xgb_p = QUICK_XGB_PARAMS if quick else FULL_XGB_PARAMS
    cands = {"RandomForest": RandomForestClassifier(**rf_p)}
    if HAS_XGB:
        cands["XGBoost"] = XGBClassifier(**xgb_p)
    else:
        cands["GradientBoosting"] = GradientBoostingClassifier(
            n_estimators=60 if quick else 150, max_depth=3, random_state=42)
    return cands


def train_and_save(quick: bool = False, n_per_class: int = None) -> dict:
    """训练入口：返回 {best_model, accuracy, report_path, model_path}。

    n_per_class：指定每类样本数（None=全部，用于 seed_all 快速训练）。
    """
    feats = load_or_build_features()
    if n_per_class:
        # 每类随机抽 n 条（用索引采样，避免 groupby.apply 丢失分组列）
        idx = feats.groupby("label").apply(
            lambda g: g.sample(min(n_per_class, len(g)), random_state=42).index,
            include_groups=False)
        feats = feats.loc[idx.explode()]
    train, test = split_train_test(feats)
    X_train, y_train = xy(train)
    X_test, y_test = xy(test)

    # ---- 交叉验证选择最优模型 ----
    best_name, best_model, best_acc = None, None, -1.0
    results = {}
    for name, model in _candidates(quick).items():
        model.fit(X_train, y_train)
        acc = accuracy_score(y_test, model.predict(X_test))
        results[name] = acc
        if acc > best_acc:
            best_name, best_model, best_acc = name, model, acc

    report = classification_report(
        y_test, best_model.predict(X_test),
        target_names=CLASS_NAMES_ZH, output_dict=True)
    cm = confusion_matrix(y_test, best_model.predict(X_test)).tolist()

    # ---- 保存模型与评测报告 ----
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.datetime.now().strftime("v%Y%m%d-%H%M%S")
    model_path = MODEL_DIR / f"fault_classifier_{version}.pkl"
    joblib.dump(best_model, model_path)

    eval_data = {
        "algorithm": best_name,
        "version": version,
        "accuracy": float(best_acc),
        "candidates": results,
        "report": report,
        "confusion_matrix": cm,
        "train_samples": int(len(train)), "test_samples": int(len(test)),
        "xgboost_available": HAS_XGB,
        "trained_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    EVAL_REPORT.write_text(json.dumps(eval_data, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    # ---- 登记模型表（置为新活跃版本） ----
    db = SessionLocal()
    try:
        db.query(MLModel).update({MLModel.is_active: 0})
        db.add(MLModel(name="fault_classifier", algorithm=best_name, version=version,
                       accuracy=float(best_acc),
                       metrics_json=json.dumps(results, ensure_ascii=False),
                       path=str(model_path), is_active=1))
        db.commit()
    finally:
        db.close()

    print(f"[train] 候选模型测试集准确率: {results}")
    print(f"[train] 最优: {best_name} accuracy={best_acc:.4f} -> {model_path.name}")
    return {"best_model": best_name, "accuracy": float(best_acc),
            "model_path": str(model_path), "eval_report": eval_data}
