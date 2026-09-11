# -*- coding: utf-8 -*-
"""
报告生成服务 —— 单设备诊断报告 / 运维周报（Markdown 导出）
============================================================
数据全部来自数据库真实记录（台账/采样/预警/预测/工单/诊断），
生成 Markdown 文本供前端下载，满足任务书"报告与导出"功能。
"""
import datetime

from sqlalchemy.orm import Session

from app.db import (Alarm, DiagnosticRecord, Equipment, Prediction,
                    SensorSample, WorkOrder)
from app.services.signal_gen import CLASS_LABELS_ZH


def device_report(db: Session, device_id: int) -> str:
    """单设备诊断报告（Markdown）"""
    dev = db.query(Equipment).filter_by(id=device_id).first()
    if not dev:
        return "# 设备报告\n\n设备不存在。"

    # 最近 10 分钟采样统计
    samples = (db.query(SensorSample)
               .filter(SensorSample.device_id == device_id)
               .order_by(SensorSample.id.desc()).limit(120).all())
    rms_vals = [s.vibration_rms for s in samples]
    temp_vals = [s.temperature for s in samples]

    latest_pred = (db.query(Prediction).filter_by(device_id=device_id)
                   .order_by(Prediction.id.desc()).first())
    latest_diag = (db.query(DiagnosticRecord).filter_by(device_id=device_id)
                   .order_by(DiagnosticRecord.id.desc()).first())
    alarms = (db.query(Alarm).filter_by(device_id=device_id)
              .order_by(Alarm.id.desc()).limit(10).all())
    orders = (db.query(WorkOrder).filter_by(device_id=device_id)
              .order_by(WorkOrder.id.desc()).limit(10).all())

    import json
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 设备诊断报告",
        "",
        f"- 报告时间：{now}",
        f"- 设备编号：{dev.code}（{dev.name}）",
        f"- 设备类型：{dev.etype} · 位置：{dev.location}",
        f"- 额定转速：{dev.rpm} rpm · 负载率：{dev.load_ratio * 100:.0f}%",
        f"- 当前健康状态：{CLASS_LABELS_ZH.get(dev.health_state, '未知')}",
        "",
        "## 1. 实时监测数据（最近 120 条采样）",
    ]
    if samples:
        lines += [
            f"- 振动 RMS：均值 {sum(rms_vals) / len(rms_vals):.4f}，"
            f"最大 {max(rms_vals):.4f}，最小 {min(rms_vals):.4f}",
            f"- 轴承温度：均值 {sum(temp_vals) / len(temp_vals):.1f}℃，"
            f"最高 {max(temp_vals):.1f}℃",
        ]
    else:
        lines.append("- 暂无采样数据（数据流引擎未运行）")

    lines += ["", "## 2. 机器学习预测"]
    if latest_pred:
        probs = [latest_pred.prob_normal, latest_pred.prob_inner,
                 latest_pred.prob_outer, latest_pred.prob_ball]
        lines += [
            f"- 预测结论：{CLASS_LABELS_ZH[latest_pred.pred_class]}",
            f"- 四类概率：正常 {probs[0]:.1%} / 内圈 {probs[1]:.1%} / "
            f"外圈 {probs[2]:.1%} / 滚动体 {probs[3]:.1%}",
            f"- 健康评分：{latest_pred.health_score:.1f} / 100",
            f"- 剩余寿命估计：{latest_pred.rul_hours:.1f} 小时" if latest_pred.rul_hours else
            "- 剩余寿命估计：未检测到退化趋势",
        ]
    else:
        lines.append("- 暂无预测记录")

    lines += ["", "## 3. 智能诊断结论"]
    if latest_diag:
        diag = json.loads(latest_diag.conclusion_json)
        evidence = json.loads(latest_diag.evidence_json)
        lines += [
            f"- 故障类型：{diag.get('fault_type', '-')}",
            f"- 置信度：{float(diag.get('confidence', 0)) * 100:.0f}%",
            f"- 诊断模式：{latest_diag.mode}（耗时 {latest_diag.latency_ms} ms）",
            f"- 数据依据：{diag.get('data_evidence', '-')}",
            "- 知识库依据：" + "；".join(f"{e['ref']}《{e['title']}》" for e in evidence)
            if evidence else "- 知识库依据：无",
        ]
        if diag.get("causes"):
            lines.append("- 原因分析：")
            lines += [f"  - {c}" for c in diag["causes"]]
    else:
        lines.append("- 暂无诊断记录")

    lines += ["", "## 4. 预警记录"]
    lines += [f"- {a.created_at.strftime('%m-%d %H:%M')} [{a.alarm_type}] "
              f"{a.message}（状态：{a.status}）" for a in alarms] or ["- 无"]

    lines += ["", "## 5. 维护工单"]
    lines += [f"- {wo.order_no} {wo.title}（{wo.status}，优先级 {wo.priority}）"
              for wo in orders] or ["- 无"]
    return "\n".join(lines) + "\n"


def weekly_report(db: Session) -> str:
    """运维周报：近 7 天预警/工单/预测统计（Markdown）"""
    since = datetime.datetime.now() - datetime.timedelta(days=7)
    alarms = db.query(Alarm).filter(Alarm.created_at >= since).all()
    orders = db.query(WorkOrder).filter(WorkOrder.created_at >= since).all()
    predictions = db.query(Prediction).filter(Prediction.ts >= since.timestamp()).count()
    devices = db.query(Equipment).all()

    from collections import Counter
    alarm_by_type = Counter(a.alarm_type for a in alarms)
    alarm_by_device = Counter(a.device_id for a in alarms)
    names = {d.id: f"{d.code} {d.name}" for d in devices}
    order_status = Counter(o.status for o in orders)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 智能车间运维周报",
        "",
        f"- 生成时间：{now}",
        f"- 统计周期：近 7 天",
        "",
        "## 1. 总体情况",
        f"- 设备总数：{len(devices)} 台，"
        f"其中故障状态 {sum(1 for d in devices if d.health_state != 0)} 台",
        f"- 预警总数：{len(alarms)} 条，活跃预警 "
        f"{sum(1 for a in alarms if a.status == 'active')} 条",
        f"- 工单总数：{len(orders)} 条（{order_status.get('已完成', 0)} 条已完成）",
        f"- 机器学习预测次数：{predictions}",
        "",
        "## 2. 预警类型分布",
    ]
    lines += [f"- {t}：{c} 条" for t, c in alarm_by_type.most_common()] or ["- 无预警"]
    lines += ["", "## 3. 预警设备排行"]
    lines += [f"- {names.get(did, did)}：{c} 条"
              for did, c in alarm_by_device.most_common(5)] or ["- 无"]
    lines += ["", "## 4. 工单执行情况"]
    lines += [f"- {s}：{c} 条" for s, c in order_status.items()] or ["- 无工单"]
    return "\n".join(lines) + "\n"
