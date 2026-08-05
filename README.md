# painterAgent — 多轮修图 Agent

基于豆包大模型 + LangGraph 的多轮图像编辑框架，支持文生图 / 图生图 / 局部重绘（云服务 + 本地 Moebius 双模式）。

## 环境要求

- Python >= 3.11（由 [uv](https://docs.astral.sh/uv/) 管理，见 `.python-version`）
- Node.js >= 18
- PostgreSQL >= 14
- Redis >= 6

## 安装

```bash
# 1. 安装 Python 依赖（自动按 .python-version 选版本，生成 .venv 与 uv.lock）
uv sync

# 2. 前端依赖
cd frontend && npm install
```

可选本地模型依赖（按需）：

```bash
uv sync --extra local-moebius    # 本地 Moebius inpainting（需 GPU + Moebius 仓库）
uv sync --extra local-lama       # LaMa 物体移除
```

## 环境变量

| 变量 | 说明 | 必需 |
|---|---|---|
| `ARK_API_KEY` | 火山引擎 ARK API Key | 是 |
| `ARK_BASE_URL` | ARK API 地址 | 否 |
| `DOUBAO_MODEL` | 豆包模型名（默认 `doubao-seedream-5-0-260128`） | 否 |
| `IMAGE_PROVIDER` | 图片生成供应商（默认 `doubao`） | 否 |
| `IMAGE_OUTPUT_DIR` | 图片输出目录（默认 `./output`） | 否 |
| `DATABASE_URL` | PostgreSQL 连接串 | 是 |
| `REDIS_URL` | Redis 连接串（默认 `redis://localhost:6379/0`） | 否 |
| `DEBUG` | 调试模式 | 否 |

```bash
cp .env.example .env   # 并填写 ARK_API_KEY / DATABASE_URL 等
```

## 初始化数据库

```bash
# 创建数据库表（postgres 用户无权访问家目录，需切换到 /tmp 执行）
cp schema.sql /tmp/
sudo -u postgres psql -d image_editor -f /tmp/schema.sql
```

## 启动

需要同时运行前后端 + Worker 三个进程：

```bash
# 终端 1 — 后端服务（默认 localhost:8000）
uv run python -m painterAgent.main

# 终端 2 — Worker（异步任务队列）
uv run python -m dramatiq painterAgent.worker --processes 1 --threads 2

# 终端 3 — 前端开发服务器（默认 localhost:5173）
cd frontend && npm run dev

# 或一键启动全部三个进程
./start-dev.sh
```

## 生产构建

```bash
# 构建前端静态文件
cd frontend && npm run build

# 后端启动后会自动挂载 frontend/dist/ 作为静态文件
# 访问 localhost:8000 即可同时获得前后端
uv run python -m painterAgent.main
```

## 目录结构

```
painterAgent/
├── src/painterAgent/       # Python 包（main / api / worker / workflow / storage / tools …）
├── frontend/            # React 前端（独立工程）
├── docs/                # 设计文档
├── output/  uploads/    # 运行时产物（gitignore）
├── schema.sql           # 数据库 DDL
└── pyproject.toml       # uv 项目定义
```
