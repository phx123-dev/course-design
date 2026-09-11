# -*- coding: utf-8 -*-
"""
多智能体编排器 —— 自研状态图引擎（接口对齐 LangGraph 状态图思想）
==================================================================
状态图（条件转移）：

  用户问诊 ──► [意图识别] ──clarify──► 澄清回复（结束）
                  │
                  ├──chat──► [知识检索] ──► 知识问答回复（结束）
                  │
                  └──diagnose──► [数据读取] ─► [知识检索] ─► [诊断推理]
                                   ─► [决策方案] ─► 流式回复 + 入库（结束）

执行模型：节点纯函数 + 共享状态（AgentState）+ 条件分支（意图类型）。
每个节点独立记录耗时/模式/备注到 trace，诊断结论与依据全量入库
（diagnostic_records），满足"可溯源"与"AI 使用披露"要求。

输出：生成器产出 (event, data) 事件序列，供 SSE 接口直接流式转发：
  start → intent → data → retrieve → diagnose → plan → token* → done
"""
import time

from app.db import ChatMessage, DiagnosticRecord
from app.services.agents import llm_client, nodes, offline, prompts
from app.services.agents.state import AgentState


def run_diagnosis(db, state: AgentState):
    """执行一次问诊。返回事件生成器。"""
    ctx = {"errors": []}
    yield ("start", {"session_id": state.session_id, "mode_hint":
                     "llm" if llm_client.is_available() else "offline"})

    # ---- 条件转移 1：意图识别 ----
    nodes.intent_node(state, db, ctx)
    yield ("intent", state.intent)

    # 澄清分支：信息不足，提示用户补充
    if state.intent["type"] == "clarify":
        reply = "请先选择要诊断的设备，或直接告诉我设备编号，例如：\n「EQ-003 振动异常，帮我诊断一下」"
        yield from _stream_text(reply)
        yield from _finish(db, state, ctx, reply)
        return

    # 咨询分支：知识问答（RAG 增强，不建工单）
    if state.intent["type"] == "chat":
        nodes.retrieve_node(state, db, ctx)
        yield ("retrieve", state.retrieved)
        reply = yield from _chat_reply(state, ctx)
        yield from _finish(db, state, ctx, reply)
        return

    # ---- 诊断主链路 ----
    nodes.data_node(state, db, ctx)
    yield ("data", {"device": state.data.get("device", {}),
                    "stats": state.data.get("recent", {}).get("stats", {}),
                    "prediction": state.data.get("prediction", {}),
                    "alarms": state.data.get("alarms", [])})

    nodes.retrieve_node(state, db, ctx)
    yield ("retrieve", state.retrieved)

    nodes.diagnose_node(state, db, ctx)
    yield ("diagnose", state.diagnosis)

    nodes.plan_node(state, db, ctx)
    yield ("plan", state.plan)

    # ---- 最终回复（流式打字机效果） ----
    reply = yield from _final_reply(state, ctx)
    yield from _finish(db, state, ctx, reply)


# ---------------- 内部：回复生成与入库 ----------------

def _stream_text(text: str, chunk: int = 6, delay: float = 0.02):
    """离线文本流式输出：模拟 LLM 打字机效果（按小块+延时）"""
    for i in range(0, len(text), chunk):
        yield ("token", text[i:i + chunk])
        time.sleep(delay)


def _chat_reply(state, ctx):
    """知识咨询回复：LLM 流式 / 离线用检索块拼装"""
    if llm_client.is_available():
        try:
            kb = "\n".join(f"{c['ref']}《{c['title']}》：{c['text']}"
                           for c in state.retrieved) or "（知识库无相关内容）"
            msgs = [
                {"role": "system", "content":
                 "你是智能车间运维知识助手。只依据提供的知识块回答，注明 [编号] 来源；"
                 "知识块无关时说明知识库暂无相关内容。回答不超过 200 字。"},
                {"role": "user", "content": f"知识块：\n{kb}\n\n用户问题：{state.query}"},
            ]
            parts = []
            for token in llm_client.stream_chat(msgs):
                parts.append(token)
                yield ("token", token)
            state.mode = "llm"
            return "".join(parts)
        except llm_client.LLMError as e:
            ctx["errors"].append(f"chat LLM 失败: {e}")

    # 离线：检索块直接作为回答（附来源）
    if state.retrieved:
        parts = ["知识库检索到以下相关内容：\n"]
        for c in state.retrieved:
            parts.append(f"{c['ref']}《{c['title']}》：{c['text'][:180]}\n")
        reply = "".join(parts)
    else:
        reply = offline.chat_reply(state.query)
    yield from _stream_text(reply)
    return reply


def _final_reply(state, ctx):
    """诊断最终回复：LLM 流式 / 离线模板流式"""
    evidence = state.retrieved
    if llm_client.is_available():
        try:
            msgs = [
                {"role": "system", "content": prompts.REPLY_SYSTEM},
                {"role": "user", "content": prompts.reply_user_prompt(
                    state.query, state.diagnosis, state.plan, evidence)},
            ]
            parts = []
            for token in llm_client.stream_chat(msgs):
                parts.append(token)
                yield ("token", token)
            return "".join(parts)
        except llm_client.LLMError as e:
            ctx["errors"].append(f"reply LLM 失败: {e}")

    reply = offline.reply_text(state.query, state.diagnosis, state.plan)
    yield from _stream_text(reply)
    return reply


def _finish(db, state: AgentState, ctx, reply: str):
    """入库：诊断记录（含 trace/证据）+ 助手消息，产出 done 事件"""
    state.reply = reply
    evidence = [{"ref": c["ref"], "title": c["title"], "source": c["source"],
                 "score": c["score"]} for c in state.retrieved]

    diagnostic_id = None
    if state.intent["type"] == "diagnose":
        import json
        rec = DiagnosticRecord(
            session_id=state.session_id, device_id=state.device_id,
            conclusion_json=json.dumps(state.diagnosis, ensure_ascii=False),
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            mode=state.mode, latency_ms=state.latency_ms,
            trace_json=json.dumps({"trace": state.trace, "errors": ctx["errors"]},
                                  ensure_ascii=False))
        db.add(rec)
        db.flush()
        diagnostic_id = rec.id

    db.add(ChatMessage(session_id=state.session_id, role="assistant",
                       content=reply,
                       evidence_json=__import__("json").dumps(evidence, ensure_ascii=False),
                       diagnostic_id=diagnostic_id))
    db.commit()

    yield ("done", {
        "reply": reply,
        "diagnostic_id": diagnostic_id,
        "evidence": evidence,
        "diagnosis": state.diagnosis,
        "plan": state.plan,
        "mode": state.mode,
        "latency_ms": state.latency_ms,
        "trace": state.trace,
    })
