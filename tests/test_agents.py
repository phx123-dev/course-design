# -*- coding: utf-8 -*-
"""多智能体编排测试：全链路诊断 / 知识咨询 / 澄清分支 / JSON 降级链 / 性能"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db import (ChatMessage, ChatSession, DiagnosticRecord, Equipment,
                    MLModel, SessionLocal, init_db)
from app.services.agents import llm_client, offline, orchestrator
from app.services.agents.state import AgentState


def _ensure_model():
    """确保存在已训练模型（全新环境跑测试时自动快速训练一次）"""
    db = SessionLocal()
    try:
        if not db.query(MLModel).filter(MLModel.is_active == 1).first():
            from app.services.ml.train import train_and_save
            train_and_save(quick=True, n_per_class=60)
    finally:
        db.close()


def _consume_events(state):
    """执行编排并收集全部事件与最终状态（自带数据库会话）"""
    db = SessionLocal()
    try:
        events = []
        for ev, data in orchestrator.run_diagnosis(db, state):
            events.append((ev, data))
        return events
    finally:
        db.close()


class TestAgents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        _ensure_model()
        db = SessionLocal()
        try:
            # 测试会话与诊断对象（EQ-003 注入外圈故障）
            dev = db.query(Equipment).filter_by(code="EQ-003").first()
            cls.device_id = dev.id
            cls._saved_state = dev.health_state
            dev.health_state = 2
            s = ChatSession(user_id=1, device_id=dev.id, title="测试会话")
            db.add(s)
            db.commit()
            cls.session_id = s.id
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        db = SessionLocal()
        try:
            db.query(Equipment).filter_by(id=cls.device_id).update(
                {Equipment.health_state: cls._saved_state})
            db.commit()
        finally:
            db.close()

    def _new_state(self, query, device_id="default"):
        # device_id="default" 用会话默认设备；None 表示显式不指定设备
        return AgentState(session_id=self.session_id, user_id=1,
                          device_id=self.device_id if device_id == "default" else device_id,
                          query=query)

    def test_full_diagnosis_pipeline(self):
        """离线模式全链路：事件序列完整、诊断与注入故障一致、依据非空、<10s"""
        state = self._new_state("EQ-003 振动异常，帮我诊断一下")
        events = _consume_events(state)
        names = [e for e, _ in events]
        for expected in ["intent", "data", "retrieve", "diagnose", "plan", "done"]:
            self.assertIn(expected, names, f"缺少事件 {expected}")
        done = dict(events)[ "done"]
        self.assertIsNotNone(done["diagnostic_id"])
        self.assertEqual(done["diagnosis"]["fault_type"], "外圈故障")
        self.assertGreater(done["diagnosis"]["confidence"], 0.5)
        self.assertGreater(len(done["evidence"]), 0, "应有知识库依据")
        self.assertLess(done["latency_ms"], 10000, "任务书要求诊断响应 ≤10s")
        self.assertIn(state.mode, ("offline", "llm"))
        # 入库检查：诊断记录 + 助手消息
        db = SessionLocal()
        try:
            rec = db.query(DiagnosticRecord).filter_by(id=done["diagnostic_id"]).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.mode, done["mode"])
            self.assertIn("trace", rec.trace_json)
            msg = (db.query(ChatMessage).filter_by(session_id=self.session_id,
                                                   diagnostic_id=rec.id).first())
            self.assertIsNotNone(msg)
        finally:
            db.close()

    def test_knowledge_chat_branch(self):
        """知识咨询分支：走 RAG 检索并回复，不产生诊断记录"""
        state = self._new_state("内圈故障有什么特征？")
        events = _consume_events(state)
        names = [e for e, _ in events]
        self.assertIn("retrieve", names)
        self.assertNotIn("diagnose", names)
        done = dict(events)["done"]
        self.assertIsNone(done["diagnostic_id"])
        self.assertIn("内圈", done["reply"])

    def test_clarify_branch(self):
        """未指明设备：澄清分支，提示补充设备信息"""
        state = self._new_state("帮我看看设备状态", device_id=None)
        events = _consume_events(state)
        names = [e for e, _ in events]
        self.assertIn("intent", names)
        done = dict(events)["done"]
        self.assertIn("请先选择", done["reply"])

    def test_intent_rules(self):
        self.assertEqual(offline.intent("EQ-003 振动异常，帮我诊断一下")["type"], "diagnose")
        self.assertEqual(offline.intent("内圈故障有什么特征")["type"], "chat")
        self.assertEqual(offline.extract_device("EQ-005 温度高"), 5)
        self.assertEqual(offline.extract_device("3号设备振动大"), 3)

    def test_json_fallback_chain(self):
        """JSON 四级降级链：正常/前后缀/截断修复/彻底失败"""
        obj, lv = llm_client.extract_json('{"fault_type": "内圈故障", "confidence": 0.9}')
        self.assertEqual(lv, 1)
        self.assertEqual(obj["fault_type"], "内圈故障")
        obj, lv = llm_client.extract_json('结论如下：{"a": 1} 以上。')
        self.assertEqual(lv, 2)
        self.assertEqual(obj["a"], 1)
        obj, lv = llm_client.extract_json('{"fault_type": "外圈故障", "causes": ["原因1", "原因2')
        self.assertEqual(lv, 3)
        self.assertEqual(obj["fault_type"], "外圈故障")
        obj, lv = llm_client.extract_json("完全不是JSON的内容")
        self.assertIsNone(obj)
        self.assertEqual(lv, 4)


if __name__ == "__main__":
    unittest.main()
