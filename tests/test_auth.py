# -*- coding: utf-8 -*-
"""认证与权限测试：登录/错误密码/令牌/角色限制"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient

from app.main import app


class TestAuth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["status"], "ok")

    def test_login_ok(self):
        r = self.client.post("/api/auth/login",
                             json={"username": "engineer", "password": "123456"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["code"], 0)
        self.assertTrue(body["data"]["token"])
        self.assertEqual(body["data"]["user"]["role"], "engineer")

    def test_login_wrong_password(self):
        r = self.client.post("/api/auth/login",
                             json={"username": "engineer", "password": "wrong"})
        self.assertEqual(r.status_code, 401)

    def test_me_with_token(self):
        login = self.client.post("/api/auth/login",
                                 json={"username": "manager", "password": "123456"}).json()
        token = login["data"]["token"]
        r = self.client.get("/api/auth/me",
                            headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["username"], "manager")

    def test_no_token_401(self):
        r = self.client.get("/api/devices")
        self.assertEqual(r.status_code, 401)

    def test_role_permission(self):
        """engineer 写设备台账应被 403 拒绝；admin 可以"""
        e = self.client.post("/api/auth/login",
                             json={"username": "engineer", "password": "123456"}).json()
        a = self.client.post("/api/auth/login",
                             json={"username": "admin", "password": "123456"}).json()
        eh = {"Authorization": f"Bearer {e['data']['token']}"}
        ah = {"Authorization": f"Bearer {a['data']['token']}"}
        payload = {"code": "EQ-TEST-01", "name": "测试设备", "etype": "电机",
                   "location": "测试区", "rpm": 1500}
        self.assertEqual(self.client.post("/api/devices", json=payload, headers=eh).status_code, 403)
        r = self.client.post("/api/devices", json=payload, headers=ah)
        self.assertEqual(r.status_code, 200)
        # 清理测试数据
        did = r.json()["data"]["id"]
        self.client.delete(f"/api/devices/{did}", headers=ah)


if __name__ == "__main__":
    unittest.main()
