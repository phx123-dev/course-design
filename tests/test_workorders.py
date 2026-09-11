# -*- coding: utf-8 -*-
"""工单管理测试：CRUD / 状态流转合法性 / 诊断自动派单 / 报告导出"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app


class TestWorkOrders(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        login = cls.client.post("/api/auth/login",
                                json={"username": "engineer", "password": "123456"}).json()
        cls.headers = {"Authorization": f"Bearer {login['data']['token']}"}

    def test_create_and_flow(self):
        """建单 → 待处理 → 进行中 → 已完成，时间戳记录"""
        r = self.client.post("/api/workorders", json={
            "device_id": 1, "title": "测试工单", "wtype": "维修",
            "description": "单元测试创建", "priority": "高"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        wo = r.json()["data"]
        self.assertEqual(wo["status"], "待处理")
        self.assertTrue(wo["order_no"].startswith("WO-"))

        r2 = self.client.put(f"/api/workorders/{wo['id']}/status",
                             json={"status": "进行中"}, headers=self.headers)
        self.assertEqual(r2.json()["data"]["status"], "进行中")
        self.assertTrue(r2.json()["data"]["started_at"])

        r3 = self.client.put(f"/api/workorders/{wo['id']}/status",
                             json={"status": "已完成"}, headers=self.headers)
        self.assertEqual(r3.json()["data"]["status"], "已完成")
        self.assertTrue(r3.json()["data"]["finished_at"])

        r4 = self.client.put(f"/api/workorders/{wo['id']}/status",
                             json={"status": "非法状态"}, headers=self.headers)
        self.assertEqual(r4.status_code, 422)

    def test_diagnosis_source_workorder(self):
        """诊断自动派单：source=diagnosis 携带 diagnostic_id"""
        r = self.client.post("/api/workorders", json={
            "device_id": 2, "title": "诊断派单测试", "wtype": "维修",
            "description": "来自智能诊断", "priority": "中",
            "source": "diagnosis", "diagnostic_id": 1}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["source"], "diagnosis")

    def test_filter_by_status(self):
        r = self.client.get("/api/workorders",
                            params={"status": "待处理"}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        for w in r.json()["data"]:
            self.assertEqual(w["status"], "待处理")

    def test_reports(self):
        """设备报告与周报导出（Markdown 内容）"""
        r = self.client.get("/api/reports/device/1", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertIn("# 设备诊断报告", r.text)
        r2 = self.client.get("/api/reports/weekly", headers=self.headers)
        self.assertEqual(r2.status_code, 200)
        self.assertIn("# 智能车间运维周报", r2.text)


if __name__ == "__main__":
    unittest.main()
