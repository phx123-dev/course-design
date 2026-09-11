# -*- coding: utf-8 -*-
"""
智能体状态对象 —— 自研状态图编排器的共享状态
============================================
接口对齐 LangGraph 的 State 思想：节点函数 (state, ctx) -> state 的纯函数式流转，
节点间通过状态对象传递中间结果，条件转移由编排器根据 state 字段决定。
若需迁移 LangGraph，仅需把各节点函数注册为 LangGraph Node 即可。
"""
import time


class AgentState:
    """一次诊断问诊的完整状态"""

    def __init__(self, session_id: int, user_id: int, device_id: int, query: str):
        self.session_id = session_id
        self.user_id = user_id
        self.device_id = device_id
        self.query = query

        # 意图识别节点输出
        self.intent = {"type": "diagnose", "device_id": device_id, "summary": query}
        # 数据读取节点输出
        self.data = {}            # {samples, features, prediction, waveform}
        # 知识检索节点输出
        self.retrieved = []       # [{ref,title,source,text,score}]
        # 诊断推理节点输出
        self.diagnosis = {}       # {fault_type, confidence, causes, evidence_refs, data_evidence}
        # 决策方案节点输出
        self.plan = {}            # {actions, spare_parts, priority, work_order}
        # 最终回复文本（流式输出）
        self.reply = ""
        # 运行模式与轨迹（可溯源 + AI 使用披露素材）
        self.mode = "offline"     # llm | offline
        self.trace = []           # [{node, mode, ms, note}]
        self.started_at = time.time()

    def add_trace(self, node: str, mode: str, ms: float, note: str = ""):
        self.trace.append({"node": node, "mode": mode, "ms": round(ms, 1), "note": note})

    @property
    def latency_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id, "device_id": self.device_id,
            "query": self.query, "intent": self.intent, "data": self.data,
            "retrieved": self.retrieved, "diagnosis": self.diagnosis,
            "plan": self.plan, "mode": self.mode,
            "trace": self.trace, "latency_ms": self.latency_ms,
        }
