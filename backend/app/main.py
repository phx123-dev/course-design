# -*- coding: utf-8 -*-
"""
FastAPI 主装配 —— 前后端集成枢纽
=================================
- 路由：/api/* 各业务模块（认证/设备/监测/预测/知识库/对话/工单/报告/看板）
- WebSocket：/ws/device/{id} 实时数据推送
- 静态托管：/ 直接伺服 frontend/（免构建 SPA，单服务部署）
- 启动初始化：建表 + 基础种子（幂等）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR, settings
from app.db import init_db, seed_basic, SessionLocal
from app.routers import auth, dashboard, devices, monitoring, prediction
from app.routers.monitoring import alarm_router, monitor_router, sensor_router
from app.websocket import router as ws_router

app = FastAPI(
    title="智能车间设备故障诊断与预测性维护系统",
    description="基于大模型多智能体的智能车间设备故障诊断与预测性维护系统 API",
    version="1.0.0",
)

# 开发期跨域（前端可独立调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 业务路由（按里程碑逐步挂载）
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(monitor_router)
app.include_router(sensor_router)
app.include_router(alarm_router)
app.include_router(dashboard.router)
app.include_router(prediction.router)
app.include_router(ws_router)


@app.on_event("startup")
def startup_init():
    """启动初始化：建表 + 基础种子 + 自动开启数据流引擎（幂等）"""
    init_db()
    db = SessionLocal()
    try:
        seed_basic(db)
    finally:
        db.close()
    from app.services.stream_service import stream_engine
    stream_engine.start()


@app.get("/api/health")
def health():
    """健康检查（e2e 测试首站）"""
    return {"code": 0, "data": {
        "status": "ok",
        "llm_mode": "llm" if settings.deepseek_api_key else "offline",
    }}


# 前端静态资源（免构建 SPA）：放最后挂载，避免拦截 /api 路径
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
