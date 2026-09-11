# -*- coding: utf-8 -*-
"""
离线模拟模式 —— 无 API Key / LLM 调用失败时的规则+模板降级
============================================================
设计目标：离线时诊断链路完整可用（任务书要求"降级兜底"）：
  - 意图识别：关键词规则（诊断/咨询/寒暄分类 + 设备提取）；
  - 诊断结论：直接采用机器学习预测结果（可解释、确定性），置信度=模型概率；
  - 原因分析：从知识库检索块中抽取"原因/处置"条目（保证依据真实可溯源）；
  - 方案与回复：按故障类型模板 + 知识块内容填充。
所有输出字段与 LLM 模式完全一致，前端无感知差异。
"""
import re

DIAGNOSE_KEYWORDS = ["诊断", "故障", "异常", "振动", "温度", "异响", "噪音",
                     "噪声", "怎么回事", "出问题", "报警", "预警", "检查一下", "帮忙看"]
CHAT_KEYWORDS = ["你好", "谢谢", "帮助", "功能", "有哪些", "介绍一下", "怎么用", "是什么"]
# 知识咨询类问法（优先于诊断关键词判断，如"内圈故障有什么特征"是咨询而非诊断）
KNOWLEDGE_PATTERNS = ["什么特征", "有什么特征", "是什么", "介绍一下", "有哪些",
                      "怎么处理", "如何", "是什么原因", "什么意思"]


def intent(query: str) -> dict:
    """规则意图识别（LLM 模式同样先走规则，保证速度与确定性）"""
    q = query.strip()
    if any(k in q for k in KNOWLEDGE_PATTERNS):
        return {"type": "chat", "summary": q}
    is_diag = any(k in q for k in DIAGNOSE_KEYWORDS)
    if is_diag:
        return {"type": "diagnose", "summary": q}
    if any(k in q for k in CHAT_KEYWORDS):
        return {"type": "chat", "summary": q}
    # 兜底：默认按诊断处理（系统主业）
    return {"type": "diagnose", "summary": q}


def extract_device(query: str) -> int:
    """从问诊文本提取设备编号：EQ-003 / 3号设备 / 3号机"""
    m = re.search(r"EQ-(\d+)", query, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*号(?:设备|机)", query)
    if m:
        return int(m.group(1))
    return None


def _extract_section(text: str, keywords: list, max_items: int = 3) -> list:
    """从知识块文本中抽取带序号的原因/处置条目"""
    lines = [ln.strip().lstrip("0123456789.、- ") for ln in text.split("\n")]
    items, in_section = [], False
    for ln in lines:
        if not ln:
            in_section = False
            continue
        if any(k in ln for k in keywords) and len(ln) < 30:
            in_section = True
            continue
        if in_section and len(ln) > 6:
            items.append(ln)
            if len(items) >= max_items:
                break
    return items


def diagnosis(prediction: dict, chunks: list) -> dict:
    """离线诊断：以 ML 预测为结论，知识块为原因依据"""
    if not prediction or not prediction.get("available"):
        return {
            "fault_type": "数据不足", "confidence": 0.0,
            "causes": ["模型未训练或数据不可用，请先运行 train.bat 或检查数据流引擎"],
            "evidence_refs": [], "data_evidence": "无可用预测数据", "note": "数据不足，置信度置零",
        }
    probs = prediction["probs"]
    top = max(probs, key=probs.get)
    conf = probs[top]

    # 从知识块抽取原因（找"原因"小节；无则用故障特征描述）
    causes = []
    for c in chunks:
        items = _extract_section(c["text"], ["原因", "常见原因", "故障机理"], 2)
        if items and not causes:
            causes = items
    if not causes:
        causes = [c["text"][:80] for c in chunks[:1]] or ["参见知识库依据"]

    data_ev = (f"模型 {prediction['model']} 判定 {top} 概率 {conf:.0%}，"
               f"健康评分 {prediction['health_score']}，"
               f"RMS≈{prediction.get('rms_hint', '见数据')}，温度≈{prediction.get('temp_hint', '见数据')}")
    return {
        "fault_type": top, "confidence": round(conf, 3), "causes": causes,
        "evidence_refs": [c["ref"] for c in chunks],
        "data_evidence": data_ev,
        "note": "离线模式：结论来自机器学习模型，依据来自知识库检索",
    }


# 各故障类型的预案（知识库未命中时的模板兜底）
FALLBACK_PLANS = {
    "内圈故障": {
        "actions": ["安排计划停机，缩短点检周期", "更换轴承并检查轴颈配合尺寸",
                    "检查润滑系统供油", "更换后跑合并复测振动温度"],
        "spare_parts": ["同型号深沟球轴承", "润滑脂", "轴用挡圈/密封圈"],
        "priority": "高", "suggest_wtype": "维修", "suggest_title": "主轴轴承内圈故障维修",
    },
    "外圈故障": {
        "actions": ["加密监测频次并准备备件", "计划停机更换轴承",
                    "检查轴承座孔配合与磨损", "更换后对中检查并复测"],
        "spare_parts": ["同型号轴承", "轴承座衬套（如磨损）", "密封件/润滑脂"],
        "priority": "高", "suggest_wtype": "维修", "suggest_title": "轴承外圈故障维修",
    },
    "滚动体故障": {
        "actions": ["立即停机（发展速度快）", "更换整套轴承并清理轴承座内腔",
                    "检查润滑脂铁屑含量", "评估同批次其他设备风险"],
        "spare_parts": ["同型号轴承", "润滑脂", "保持架"],
        "priority": "高", "suggest_wtype": "更换", "suggest_title": "轴承滚动体故障紧急更换",
    },
    "正常": {
        "actions": ["继续保持日常点检", "按周期执行润滑维护"],
        "spare_parts": [], "priority": "低", "suggest_wtype": "点检", "suggest_title": "设备定期点检",
    },
    "润滑不良": {
        "actions": ["缩短点检周期并安排补脂", "检查润滑脂状态与密封",
                    "若温度持续升高则停机清洗重新加脂"],
        "spare_parts": ["规定型号润滑脂", "密封圈/油封", "清洗剂"],
        "priority": "中", "suggest_wtype": "润滑", "suggest_title": "轴承润滑处理",
    },
}


def plan(fault_type: str, chunks: list) -> dict:
    """离线方案：优先抽取知识块"处置建议"，无命中用模板兜底"""
    actions, parts = [], []
    for c in chunks:
        acts = _extract_section(c["text"], ["处置建议", "维修处置", "处理"], 3)
        if acts:
            actions = acts
        sp = _extract_section(c["text"], ["备件清单", "备件"], 3)
        if sp:
            parts = sp
    fb = FALLBACK_PLANS.get(fault_type, FALLBACK_PLANS["内圈故障"])
    return {
        "actions": actions or fb["actions"],
        "spare_parts": parts or fb["spare_parts"],
        "priority": fb["priority"],
        "suggest_wtype": fb["suggest_wtype"],
        "suggest_title": fb["suggest_title"],
    }


def reply_text(query: str, diagnosis: dict, plan: dict) -> str:
    """离线最终回复模板（字段与 LLM 回复结构一致）"""
    d = diagnosis
    p = plan
    lines = [
        "【诊断结论】",
        f"判断为「{d['fault_type']}」，置信度 {d['confidence']:.0%}。",
        "",
        "【数据依据】",
        d.get("data_evidence", ""),
    ]
    if d.get("causes"):
        lines += ["", "【原因分析】"] + [f"· {c}" for c in d["causes"]]
    if p.get("actions"):
        lines += ["", "【处置建议】"] + [f"{i + 1}. {a}" for i, a in enumerate(p["actions"])]
    if p.get("spare_parts"):
        lines.append("备件：" + "、".join(p["spare_parts"]))
    if d.get("note"):
        lines += ["", f"（{d['note']}）"]
    return "\n".join(lines)


def chat_reply(query: str) -> str:
    """非诊断类咨询的离线回复"""
    return ("我是智能车间运维助手，可以帮你：\n"
            "1. 诊断设备故障：如「EQ-003 振动异常，帮我诊断一下」\n"
            "2. 咨询设备知识：如「内圈故障有什么特征」\n"
            "3. 生成维护工单：诊断后一键派单\n"
            "请在上方选择设备或直接描述问题。")
