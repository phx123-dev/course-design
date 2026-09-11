# -*- coding: utf-8 -*-
"""
端到端全业务闭环测试（需先启动服务：start.bat 或 uvicorn）
================================================================
仅用 Python 标准库（urllib），模拟真实浏览器调用：
健康检查 → 登录 → 台账 → 数据流 → 实时快照 → 机器学习预测
→ 知识库检索 → SSE 多智能体诊断（断言 <10s）→ 诊断派单
→ 工单流转 → 报告导出 → 看板聚合。
运行：PYTHONIOENCODING=utf-8 py -3.13 tests/test_api_e2e.py
"""
import codecs
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} {detail}")


def req(method, path, token=None, body=None):
    """标准库 HTTP 请求封装"""
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main():
    print("== 端到端全业务闭环测试 ==")

    # 1. 健康检查
    code, body = req("GET", "/api/health")
    check("健康检查", code == 200 and json.loads(body)["data"]["status"] == "ok")

    # 2. 登录
    code, body = req("POST", "/api/auth/login", body={"username": "engineer", "password": "123456"})
    login = json.loads(body)
    token = login["data"]["token"]
    check("登录获取令牌", code == 200 and bool(token) and login["data"]["user"]["role"] == "engineer")

    # 3. 设备台账
    code, body = req("GET", "/api/devices", token=token)
    devices = json.loads(body)["data"]
    check("设备台账列表", code == 200 and len(devices) >= 6, f"实际 {len(devices)} 台")

    # 4. 数据流引擎
    req("POST", "/api/monitoring/start", token=token)
    time.sleep(3)
    code, body = req("GET", "/api/monitoring/realtime", token=token)
    rt = json.loads(body)["data"]
    check("实时数据快照（流引擎）", code == 200 and len(rt) >= 6 and all("rms" in s for s in rt),
          f"实际 {len(rt)} 台")

    # 5. 机器学习预测
    code, body = req("POST", "/api/prediction/1/run", token=token)
    pred = json.loads(body)["data"]
    probs = [pred["prob_normal"], pred["prob_inner"], pred["prob_outer"], pred["prob_ball"]]
    check("机器学习预测接口", code == 200 and pred.get("available")
          and abs(sum(probs) - 1.0) < 0.01,
          f"模型={pred.get('model')} 结论={pred.get('pred_label')}")

    # 6. 知识库检索
    code, body = req("POST", "/api/knowledge/search", token=token,
                     body={"query": "内圈故障特征", "top_k": 5})
    hits = json.loads(body)["data"]
    check("知识库混合检索", code == 200 and len(hits) > 0 and hits[0]["ref"] == "[1]",
          f"命中 {len(hits)} 条")

    # 7. SSE 多智能体诊断（测量端到端耗时）
    print("  …… 多智能体诊断中（SSE 流式）")
    t0 = time.time()
    payload = json.dumps({"device_id": 1, "message": "EQ-001 振动异常，帮我诊断一下"}).encode("utf-8")
    r = urllib.request.Request(BASE + "/api/chat/messages", data=payload,
                               headers={"Content-Type": "application/json",
                                        "Authorization": f"Bearer {token}"}, method="POST")
    events, reply_tokens = [], []
    decoder = codecs.getincrementaldecoder("utf-8")()   # 多字节字符跨块解码
    with urllib.request.urlopen(r, timeout=60) as resp:
        buf = ""
        for chunk in iter(lambda: resp.read(1024), b""):
            buf += decoder.decode(chunk)
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                ev, data = None, None
                for line in raw.split("\n"):
                    if line.startswith("event:"):
                        ev = line[6:].strip()
                    elif line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            pass
                if ev:
                    events.append((ev, data))
                    if ev == "token":
                        reply_tokens.append(data)
    latency_ms = int((time.time() - t0) * 1000)
    done = dict(events).get("done", {})
    check("SSE 事件序列完整（start/intent/data/retrieve/diagnose/plan/done）",
          all(e in [x[0] for x in events]
              for e in ["start", "intent", "data", "retrieve", "diagnose", "plan", "done"]))
    check("流式回复非空", len("".join(reply_tokens)) > 50)
    check("诊断耗时 ≤ 10s（任务书验收）", latency_ms < 10000, f"实际 {latency_ms} ms")
    check("诊断结果含依据溯源", len(done.get("evidence", [])) > 0)
    diagnostic_id = done.get("diagnostic_id")
    check("诊断记录已入库", diagnostic_id is not None)

    # 8. 诊断一键派单
    code, body = req("POST", "/api/workorders", token=token, body={
        "device_id": 1, "title": done.get("plan", {}).get("suggest_title", "诊断维修工单"),
        "wtype": "维修", "description": done.get("reply", ""),
        "priority": done.get("plan", {}).get("priority", "中"),
        "source": "diagnosis", "diagnostic_id": diagnostic_id})
    wo = json.loads(body)["data"]
    check("诊断自动派单", code == 200 and wo["source"] == "diagnosis" and wo["order_no"].startswith("WO-"))

    # 9. 工单状态流转
    code, _ = req("PUT", f"/api/workorders/{wo['id']}/status", token=token, body={"status": "进行中"})
    check("工单流转 待处理→进行中", code == 200)
    code, body = req("PUT", f"/api/workorders/{wo['id']}/status", token=token, body={"status": "已完成"})
    check("工单流转 进行中→已完成", code == 200 and json.loads(body)["data"]["finished_at"])

    # 10. 报告导出
    code, body = req("GET", "/api/reports/device/1", token=token)
    check("单设备诊断报告导出", code == 200 and "# 设备诊断报告" in body)
    code, body = req("GET", "/api/reports/weekly", token=token)
    check("运维周报导出", code == 200 and "# 智能车间运维周报" in body)

    # 11. 看板聚合
    code, body = req("GET", "/api/dashboard/overview", token=token)
    stats = json.loads(body)["data"]["stats"]
    check("健康看板聚合", code == 200 and stats["device_total"] >= 6)

    # 12. 权限：未登录 401
    code, _ = req("GET", "/api/devices")
    check("未登录接口拒绝（401）", code == 401)

    print(f"\n== e2e 结果: {len(PASS)} PASS / {len(FAIL)} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
