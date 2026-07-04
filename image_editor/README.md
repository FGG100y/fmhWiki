# 多轮修图 Agent

基于豆包大模型 + LangGraph 的多轮图像编辑框架。

## 环境要求

- Python >= 3.11
- Node.js >= 18
- PostgreSQL >= 14
- Redis >= 6
- 包管理二选一：[UV](https://docs.astral.sh/uv/) 或 [pyenv](https://github.com/pyenv/pyenv)

## Python 环境（pyenv，可选）

若不使用 UV，可用 pyenv 管理 Python 版本与虚拟环境：

```bash
# 安装并切换到所需 Python 版本
pyenv install 3.11.9
pyenv local 3.11.9          # 在 image_editor/ 目录下写入 .python-version

# 创建并激活虚拟环境
pyenv virtualenv 3.11.9 image-editor
pyenv local image-editor    # 自动激活该虚拟环境
```

## 安装 PostgreSQL

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install postgresql postgresql-client

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 创建数据库（注意：postgres 用户无权访问你的家目录，需切换到 /tmp 执行）
cd /tmp && sudo -u postgres createdb image_editor

# 设置密码
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'your_password';"
```

## 安装 Redis

```bash
# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis

# 或使用 Docker（推荐）
docker run -d --name redis -p 6379:6379 redis:7

# 验证
redis-cli ping  # 应返回 PONG
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

## 初始化数据库

```bash
# 复制环境变量模板并填写密码
cp .env.example .env

# 创建数据库表（需切换到 /tmp 执行，否则 postgres 用户无权访问家目录）
cp schema.sql /tmp/
sudo -u postgres psql -d image_editor -f /tmp/schema.sql
```

## 安装依赖

```bash
# Python 依赖（在 image_editor/ 目录下）
uv sync                     # 使用 UV
# 或（pyenv 虚拟环境已激活时）
pip install -e .

# 前端依赖
cd frontend && npm install
```

## 启动

需要同时运行前后端 + Worker 三个进程：

```bash
# 终端 1 — 后端服务（默认 localhost:8000）
uv run python -m image_editor.main    # 使用 UV
# 或（pyenv 虚拟环境已激活时）
python -m image_editor.main

# 终端 2 — Worker（异步任务队列）
uv run python -m dramatiq image_editor.worker    # 使用 UV
# 或（pyenv 虚拟环境已激活时）
python -m dramatiq image_editor.worker

# 终端 3 — 前端开发服务器（默认 localhost:5173）
cd frontend && npm run dev
```

## 生产构建

```bash
# 构建前端静态文件
cd frontend && npm run build

# 后端启动后会自动挂载 frontend/dist/ 作为静态文件
# 访问 localhost:8000 即可同时获得前后端
uv run python -m image_editor.main    # 使用 UV
# 或（pyenv 虚拟环境已激活时）
python -m image_editor.main
```
