# phx 项目规则 —— 基于大模型多智能体的智能车间设备故障诊断与预测性维护系统

制造智能技术课程设计项目。选题说明、方案设计与任务书见根目录《选题说明.md》《方案设计.md》《制造智能技术课程设计任务书(1).pdf》。

## 架构约定

- 后端：Python 3.13 + FastAPI + SQLAlchemy(SQLite)，分层：routers(API) → services(业务/算法) → db(数据层)
- 三大技术方向：
  - **大模型/多智能体**：`services/agents/` 自研状态图编排器（5 节点 + 条件分支 + 离线降级双模）
  - **机器学习**：`services/ml/` 振动信号特征工程 + XGBoost/随机森林故障分类 + 孤立森林/3σ 异常 + RUL 退化拟合
  - **数据库**：13 张表（设备台账/时序采样/工单/知识库/会话/诊断记录），SQLAlchemy ORM
- RAG：自研轻量实现（jieba 分词 + 特征哈希向量化 + numpy 余弦检索，混合关键词打分）；
  向量库/编排器均留抽象位，可替换 Chroma/LangGraph
- 前端：Vue3 + Element Plus + ECharts + axios 全本地 CDN（`frontend/libs/`），免构建 SPA；
  页面组件在 `assets/pages2.js`，公共组件在 `assets/components.js`
- 知识语料：`knowledge/*.md`（轴承故障案例/设备手册/SOP），`backend/scripts/seed_all.py` 入库
- 生成数据：`data/processed/`（phx.db、特征 CSV、模型 .pkl，由 seed_all.py 一键重建，不提交）
- LLM：DeepSeek（OpenAI 兼容，httpx 直调），Key 在 `.env`；无 Key 自动离线模拟模式

## 提交规范

- 小步提交，中文提交说明，格式 `<type>: <简述>`（type：init/docs/data/feat/test/fix）
- 一个里程碑一个（或少量）提交，保持每个提交可运行可测试

## 测试命令

- 单测：`cd backend && PYTHONIOENCODING=utf-8 py -3.13 -m unittest discover -s ../tests -p "test_*.py"`
- e2e：先启动服务（`start.bat`），再 `PYTHONIOENCODING=utf-8 py -3.13 tests/test_api_e2e.py`
- 前端挂载：`cd tests && npm install && node frontend_mount_test.js`
- 模型训练：`train.bat`（全量）或 `cd backend && py -3.13 scripts/seed_all.py --quick`

## 启动

- `start.bat`（检查端口后启动）或 `cd backend && py -3.13 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 页面 http://localhost:8000 ，API 文档 http://localhost:8000/docs
- 种子账号：admin / engineer / manager（密码 123456）

## 过程档案

- 每阶段更新 `prompt/session-<YYYY-MM-DD>.json` 会话日志（上下文压缩前先备份）
- 数据来源如实披露：模拟振动信号 + 自建知识语料（合成公式见设计报告"数据资源构建"章），CWRU 仅作可选补充脚本
