# 基于大模型多智能体的智能车间设备故障诊断与预测性维护系统

> 《制造智能技术》课程设计 · 智能制造工程专业
> 技术方向：①大模型/多智能体（AI） ②机器学习 ③数据库（另含工业物联网数据处理与 Web 可视化）

面向智能车间关键设备（轴承/旋转机械、数控机床）的运维辅助系统：**数据接入 → 实时监控 → 机器学习预测 → 多智能体诊断（RAG 知识增强）→ 维护工单闭环 → 对话式交互**。

## 快速开始

### 一键初始化（首次运行）

```bat
setup.bat        REM 创建 Python3.13 虚拟环境 + 安装依赖 + 生成数据与快速训练模型
start.bat        REM 启动系统并打开浏览器
```

- Web UI：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 演示账号：`admin`（系统管理员）/ `engineer`（维护工程师）/ `manager`（车间管理员），密码均为 `123456`

### 手动方式

```bash
py -3.13 -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
cd backend
set PYTHONIOENCODING=utf-8
..\.venv\Scripts\python scripts\seed_all.py --quick   # 生成数据库/数据/快速训练模型
..\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 大模型配置（可选）

复制 `.env.example` 为 `.env`，填入 DeepSeek API Key。**不配置也能完整演示**——系统自动进入离线模拟模式（规则 + 模板 + 知识检索 + ML 预测结果填充），LLM 与离线两种模式走相同的多智能体编排流程。

## 功能一览

| 模块 | 说明 |
| --- | --- |
| 登录与角色权限 | 维护工程师 / 车间管理员 / 系统管理员 三种角色 |
| 设备台账管理 | 设备基础信息增删改查 |
| 实时监控 | 模拟传感器数据流（振动/温度/转速）+ WebSocket 推送 + 故障注入演示 |
| 机器学习预测 | 时域/频域特征提取、XGBoost+随机森林故障分类（≥90%）、孤立森林+3σ 异常预警、剩余寿命估计 |
| 多智能体诊断 | 意图识别→数据读取→知识检索→诊断推理→决策方案 五节点编排，结论可溯源 |
| RAG 知识库 | 设备手册/维修案例/SOP 语料，上传、切分、向量化、混合检索 |
| 维护工单 | 诊断一键派单、状态流转（待处理/进行中/已完成） |
| 对话式交互 | 自然语言问诊、SSE 流式回复、依据溯源卡片 |
| 报告导出 | 单设备诊断报告、运维周报 |

## 测试

```bash
cd backend
set PYTHONIOENCODING=utf-8
..\.venv\Scripts\python -m unittest discover -s ../tests -p "test_*.py"   # 单元测试
# 端到端：先 start.bat 启动服务，再执行
..\.venv\Scripts\python ../tests/test_api_e2e.py
```

## 项目结构

```
backend/     FastAPI 后端（routers → services → db 分层；ml/ rag/ agents/ 三大算法模块）
frontend/    Vue3 + Element Plus + ECharts 免构建 SPA（本地 CDN 库）
knowledge/   知识库语料（中文 md：故障案例/设备手册/SOP）
data/        生成数据（不入库，seed_all.py 重建）
prompt/      AI 会话过程档案（任务书要求）
tests/       自动化测试（unittest + e2e + 前端挂载测试）
docs/        需求规格说明书 / 设计报告 / 演示脚本 / 任务书
```

## 数据说明（如实披露）

- 传感器数据：Python 模拟振动信号生成器合成（按轴承特征频率 BPFI/BPFO/BSF 构造冲击信号 + 噪声 + 工况参数），**非企业真实数据**；`backend/scripts/load_cwru.py` 提供公开 CWRU 数据集的可选补充加载。
- 知识库语料：依据公开资料整理的设备手册/维修案例/SOP 文本。

## 过程档案

- git 提交历史（小步提交，中文说明）
- `prompt/session-*.json` AI 会话日志
