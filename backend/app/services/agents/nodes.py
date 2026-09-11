# -*- coding: utf-8 -*-
"""
智能体节点实现 —— 意图识别 / 数据读取 / 知识检索 / 诊断推理 / 决策方案
======================================================================
每个节点 = 纯函数 (state, db, ctx) -> state，输入输出都通过状态对象传递，
与 LangGraph 的 Node 概念一一对应（可替换位）。

双模设计：每个"智能"节点先尝试 LLM 模式，失败自动降级离线模板，
节点级 trace 记录所用模式与耗时（供报告"AI 使用披露"与依据溯源）。
"""
import time

from app.db import Equipment
from app.services.agents import llm_client, offline, prompts, tools
from app.services.agents.state import AgentState


# ---------------- 1. 意图识别 ----------------
def intent_node(state: AgentState, db, ctx) -> AgentState:
    t0 = time.time()
    # 规则先判（速度快且确定性好）；设备提取兜底从问诊文本正则解析
    state.intent = offline.intent(state.query)
    if not state.device_id:
        dev_id = offline.extract_device(state.query)
        if dev_id:
            state.device_id = dev_id
    state.intent["device_id"] = state.device_id
    # 无明确设备且属诊断意图 → 澄清
    if state.intent["type"] == "diagnose" and not state.device_id:
        state.intent = {"type": "clarify", "device_id": None,
                        "summary": "未指明诊断对象，请选择设备或输入设备编号（如 EQ-003）"}
    state.add_trace("intent", "rule", (time.time() - t0) * 1000,
                    f"type={state.intent['type']} device={state.intent.get('device_id')}")
    return state


# ---------------- 2. 数据读取 ----------------
def data_node(state: AgentState, db, ctx) -> AgentState:
    t0 = time.time()
    did = state.device_id
    device = tools.get_device(db, did)
    recent = tools.get_recent_data(db, did, seconds=90)
    features = tools.get_features(db, did)
    prediction = tools.run_prediction(db, did)
    alarms = tools.get_active_alarms(db, did)
    # 给离线诊断模板补充 RMS/温度提示（如实引用数据）
    if prediction.get("available"):
        stats = recent.get("stats", {})
        prediction["rms_hint"] = f"{stats.get('rms_mean', 0):.3f} (均值)"
        prediction["temp_hint"] = f"{stats.get('temp_max', 0):.1f}℃ (峰值)"
    state.data = {"device": device, "recent": recent, "features": features,
                  "prediction": prediction, "alarms": alarms}
    state.add_trace("data", "tool", (time.time() - t0) * 1000,
                    f"model_avail={prediction.get('available')}")
    return state


# ---------------- 3. 知识检索（RAG） ----------------
def retrieve_node(state: AgentState, db, ctx) -> AgentState:
    t0 = time.time()
    pred_label = state.data.get("prediction", {}).get("pred_label", "")
    query = f"{state.query} {pred_label}"
    state.retrieved = tools.search_knowledge(db, query, top_k=3)
    state.add_trace("retrieve", "rag", (time.time() - t0) * 1000,
                    f"hits={len(state.retrieved)}")
    return state


# ---------------- 4. 诊断推理 ----------------
def diagnose_node(state: AgentState, db, ctx) -> AgentState:
    t0 = time.time()
    data = state.data
    prediction = data.get("prediction", {})
    mode = "offline"
    diag = None

    if llm_client.is_available():
        try:
            user_msg = prompts.diagnose_user_prompt(
                data.get("device", {}), data.get("recent", {}), prediction, state.retrieved)
            raw = llm_client.chat(
                [{"role": "system", "content": prompts.DIAGNOSE_SYSTEM},
                 {"role": "user", "content": user_msg}],
                temperature=0.2, json_mode=True)
            obj, level = llm_client.extract_json(raw)
            if obj and obj.get("fault_type"):
                diag = obj
                mode = f"llm(L{level})"
        except llm_client.LLMError as e:
            ctx["errors"].append(f"diagnose LLM 失败: {e}")

    if diag is None:
        diag = offline.diagnosis(prediction, state.retrieved)
    state.diagnosis = diag
    state.mode = "llm" if "llm" in mode else "offline"
    state.add_trace("diagnose", mode, (time.time() - t0) * 1000,
                    f"fault={diag.get('fault_type')}")
    return state


# ---------------- 5. 决策方案 ----------------
def plan_node(state: AgentState, db, ctx) -> AgentState:
    t0 = time.time()
    mode = "offline"
    plan = None

    if llm_client.is_available():
        try:
            raw = llm_client.chat(
                [{"role": "system", "content": prompts.PLAN_SYSTEM},
                 {"role": "user", "content": prompts.plan_user_prompt(
                     state.diagnosis, state.retrieved)}],
                temperature=0.2, json_mode=True)
            obj, level = llm_client.extract_json(raw)
            if obj and obj.get("actions"):
                plan = obj
                mode = f"llm(L{level})"
        except llm_client.LLMError as e:
            ctx["errors"].append(f"plan LLM 失败: {e}")

    if plan is None:
        plan = offline.plan(state.diagnosis.get("fault_type", ""), state.retrieved)
    state.plan = plan
    state.add_trace("plan", mode, (time.time() - t0) * 1000,
                    f"actions={len(plan.get('actions', []))}")
    return state
