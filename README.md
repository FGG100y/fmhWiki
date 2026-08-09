# painterAgent — 多轮修图 Agent

基于豆包大模型 + LangGraph 的多轮图像编辑框架，支持文生图 / 图生图 / 局部重绘（云服务 + 本地 GPU 模型双模式）。前端 React SPA，后端 FastAPI + Dramatiq（Redis）+ PostgreSQL。

## 环境要求

- Python >= 3.11（由 [uv](https://docs.astral.sh/uv/) 管理）
- Node.js >= 18
- PostgreSQL >= 14
- Redis >= 6
- GPU（可选，仅本地 inpainting 需要）

## 快速开始

```bash
# 1. 安装依赖
uv sync
cd frontend && npm install

# 2. 配置环境变量
cp .env.example .env   # 填写 ARK_API_KEY / DATABASE_URL

# 3. 初始化数据库（pg 用户无法访问家目录，先拷到 /tmp）
cp schema.sql /tmp/
sudo -u postgres psql -d image_editor -f /tmp/schema.sql

# 4. 启动（三个进程）
./start-dev.sh
# 或手动：
#   终端1: uv run python -m painterAgent.main      # 后端 :8000
#   终端2: uv run python -m dramatiq painterAgent.worker --processes 1 --threads 2
#   终端3: cd frontend && npm run dev               # 前端 :5173
```

生产构建：

```bash
cd frontend && npm run build
uv run python -m painterAgent.main   # 后端自动挂载 frontend/dist/，访问 :8000 即可
```

## 架构概览

```
Browser (React SPA)
      │  REST + polling
      ▼
┌─────────────────────────────────────────────┐
│  FastAPI (api.py)                           │
│  - 同步接口: session CRUD, upload           │
│  - /execute: 创建 job → 入队 → 立即返回     │
│  - /replay:  同步重跑 workflow（调试用）     │
└──────────────┬──────────────────────────────┘
               │  enqueue (Redis)
               ▼
┌─────────────────────────────────────────────┐
│  Dramatiq Worker (worker.py)                │
│  - 从 Redis 取 job，执行 LangGraph workflow │
│  - ⚠️ 必须 --processes 1 --threads 2        │
│    （多进程会导致 GPU OOM）                  │
└──────────────┬──────────────────────────────┘
               │  async
               ▼
┌─────────────────────────────────────────────┐
│  LangGraph Workflow (workflow.py)           │
│                                             │
│  load_session → safety_check → [路由]        │
│    ├── agentic_edit (多步规划)              │
│    ├── enhance_prompt (LLM 改写提示词)       │
│    └── run_image_tool (执行图像操作)         │
│         └── visual_qa (质量评估)             │
│              └── persist_turn               │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│  ToolRouter (tools/router.py)               │
│  - resolve_task_type: 根据 image/mask 推断  │
│    generate | edit | inpaint               │
│  - select: 按 priority 选最优工具（本地优先）│
│  - invoke_with_fallback: 失败自动切换下一个  │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┬──────────────┐
    ▼          ▼          ▼              ▼
  doubao    moebius    lama          ollama
  (云端)    (本地GPU)  (本地CPU)     (本地LLM)
```

### 关键设计决策

**两级路由**：图片工具和文本 LLM 共用同一套 `ModelRoute` 注册表（`tools/router.py`），通过 `Capability` 枚举区分能力维度。文本 LLM 的优先级由 `TEXT_LLM_ORDER` 环境变量控制，图片工具由 `priority` 字段控制。

**同步 vs 异步执行**：生产路径是异步的（`/execute` → Dramatiq → Worker），前端轮询 `/jobs/{id}` 获取结果。`/replay` 是同步的，用于调试和重试，直接在 API 进程中运行 workflow。

**存储双模式**：`storage.py` 根据 `DATABASE_URL` 是否存在自动选择 `PostgresStore` 或 `MemoryStore`。无数据库时也能跑（数据不持久化），方便本地开发。

## 目录结构

```
painterAgent/
├── src/painterAgent/          # Python 包（所有后端代码）
│   ├── main.py                #   入口：拉起 uvicorn，配置日志
│   ├── api.py                 #   FastAPI 路由：session/turn/job/upload/execute/replay
│   ├── worker.py              #   Dramatiq worker：消费 Redis 队列，执行 workflow
│   ├── workflow.py            #   LangGraph 状态图：编排所有处理节点
│   ├── state.py               #   ImageEditState TypedDict 定义
│   ├── config.py              #   所有配置项（env vars → dataclass）
│   ├── storage.py             #   MemoryStore / PostgresStore 双实现
│   ├── models.py              #   Pydantic 请求/响应模型
│   ├── tasks.py               #   Dramatiq broker 配置（Redis）
│   ├── errors.py              #   错误码 → 用户友好的错误消息
│   ├── agents/                #   LangGraph 节点实现
│   │   ├── prompt_enhancer.py #     用 LLM 将用户指令改写成高质量图像提示词
│   │   ├── agentic_editor.py  #     多步编辑：规划模型自主调用工具链
│   │   ├── visual_qa.py       #     生成后质量评估（QA），控制重试
│   │   └── demo_learning.py   #     从历史编辑中学习（demo + preference）
│   ├── tools/                 #   工具实现 + 路由
│   │   ├── __init__.py        #     ⚠️ 不能为空 — 触发所有工具注册
│   │   ├── base.py            #     ImageTool 协议 + ModelRegistry
│   │   ├── router.py          #     Capability 枚举 + route 注册与选择
│   │   ├── doubao_image.py    #     豆包云端图像 API（generate/edit/inpaint）
│   │   ├── moebius_image.py   #     Moebius 本地 GPU inpainting
│   │   ├── lama_image.py      #     LaMa 本地物体移除
│   │   ├── agent_tools.py     #     Agentic 模式下的工具定义（generate/edit/verify/inspect）
│   │   └── mask.py            #     Mask 处理工具
│   └── llm/                   #   LLM 客户端
│       ├── client.py          #     DoubaoLLM + DoubaoImageClient（豆包云端）
│       ├── aisuite_client.py  #     aisuite 统一客户端（agentic 模式用）
│       ├── ollama_client.py   #     Ollama 本地 LLM 客户端
│       └── moebius_client.py  #     Moebius 模型底层调用
├── frontend/                  # React 18 + TypeScript + Vite
│   └── src/
│       ├── App.tsx            #     根组件（布局 + 状态协调）
│       ├── api.ts             #     REST API 封装
│       ├── hooks/useSession.ts#     核心状态管理（turns, upload, mask, send）
│       ├── hooks/useTheme.ts  #     亮/暗主题切换
│       └── components/        #     UI 组件
│           ├── ActivityBar.tsx    # 工具栏（生成/编辑/inpaint + agentic 开关）
│           ├── ChatHistory.tsx    # 消息气泡列表
│           ├── ChatInput.tsx      # 指令输入框 + 图片上传
│           ├── ImageViewer.tsx    # 图片前后对比展示
│           ├── MaskCanvas.tsx     # 遮罩绘制画布
│           ├── SketchCanvas.tsx   # 草图绘制画布
│           ├── TurnTimeline.tsx   # 编辑历史时间线
│           └── WelcomeGuide.tsx   # 首次使用引导
├── docs/                      # 设计文档
├── schema.sql                 # 数据库 DDL（5 张表）
├── pyproject.toml             # uv 项目定义 + 可选依赖分组
├── start-dev.sh               # 一键启动三个进程
├── .env.example               # 环境变量模板（权威参考）
└── CLAUDE.md                  # Claude Code 指令
```

## 核心流程

### 一次编辑请求的完整生命周期

```
1. 用户在前端输入指令 + 可选上传图片/绘制 mask
2. POST /sessions/{id}/execute
   - 创建 turn（status=queued）+ job
   - 入队 Dramatiq（Redis），立即返回 job_id + turn_id
3. 前端轮询 GET /jobs/{job_id}（1s 间隔）
4. Worker 取到 job → 更新 status=running → 执行 LangGraph workflow:

   load_session      从 DB 加载会话和当前图片
        │
   safety_check      关键词过滤（nude/暴力/色情…）
        │
   [条件路由]        根据 execution_mode 决定分支:
        │
        ├── agentic  多步规划（agentic_editor.py）
        │            LLM 自主决定调用 generate → edit → verify 的序列
        │            成功 → 直接 persist_turn
        │            失败 → degraded=true → 降级到 legacy 路径
        │
        ├── legacy   enhance_prompt → run_image_tool → visual_qa
        │            - enhance_prompt: LLM 改写中文为英文 + 扩展细节
        │            - run_image_tool: 选择最优工具执行（本地优先，云端兜底）
        │            - visual_qa: 质量评分 + 重试判断（最多 2 次）
        │
        └── fail     直接失败
        │
   persist_turn      结果写入 turns 表，更新 session.current_turn_id

5. Worker 更新 job status=succeeded（或 failed）
6. 前端轮询到终态 → 刷新 UI 显示新图片
```

### 工具路由策略

| 输入特征 | 任务类型 | 首选工具 | 兜底 |
|---------|---------|---------|-----|
| 无图 | `generate` | doubao（唯一选择） | — |
| 有图 + 无 mask | `edit` | doubao（唯一选择） | — |
| 有图 + 有 mask | `inpaint` | moebius（优先级 10）→ lama（9） | doubao（8） |

本地模型通过 env var 启用（`MOEBIUS_ENABLED=true` 等），未启用时直接走云端。

### Agentic vs Deterministic 模式

- **Deterministic（确定性）**：固定流程 enhance → generate/edit → QA。适合简单、明确的需求。
- **Agentic（智能体）**：LLM 自主规划多步工具调用。例如"把背景换成海滩，人物加墨镜"会被拆成两个 edit 步骤。启用需 `AGENTIC_EDIT_ENABLED=true`。
- **Auto**：`AGENTIC_EDIT_ENABLED=true` 时等同于 agentic，否则等同于 deterministic。通过前端 ActivityBar 可切换。

Agentic 模式支持降级：如果规划模型失败（无可用工具、步数超限等），自动回退到 legacy 路径。

## 数据库

5 张表，DDL 见 `schema.sql`：

| 表 | 用途 | 关键字段 |
|---|------|---------|
| `sessions` | 编辑会话 | `current_turn_id` 指向当前活跃 turn |
| `turns` | 每次编辑操作 | `parent_turn_id` 构成树形历史，`agent_steps` 存多步记录 |
| `images` | 图片元数据 | `url` 存 base64 data URI，无对象存储 |
| `jobs` | 异步任务 | `status` 流转 queued→running→succeeded/failed/cancelled |
| `model_calls` | LLM/图像 API 调用审计 | `latency_ms`, `input_tokens`, `output_tokens` |

**Turn 树**：turns 通过 `parent_turn_id` 形成树结构。同一 session 下可以有多个分支（replay 产生新子节点）。`current_turn_id` 指向当前查看的节点。

## 关键约束与陷阱

1. **Worker 进程数**：Dramatiq 默认 `cpu_count` 个进程，每个进程独立加载 Moebius → GPU OOM。**必须 `--processes 1 --threads 2`**。

2. **Moebius 模型不卸载**：`_cleanup_gpu()` 只清 CUDA cache 不释放模型参数。改完 Moebius 代码需要重启 worker 才能生效。

3. **图片存储**：images 表 `url` 字段存的是 base64 data URI，没有对象存储。上传限制 1MB / 2048px。

4. **`persist_turn` 不一定执行**：workflow 如果在 image_tool 阶段 OOM 或 API 超时，turn 可能缺少 `output_image_id`。下游代码需处理这种情况。

5. **`tools/__init__.py` 不能为空**：工具注册靠 import 副作用触发 `registry.register()`。如果这个文件为空或被跳过，所有工具静默不可用。

6. **Seedream 5.0 是唯一模型**：LLM 推理（prompt enhance）和图像生成都用同一个 `DOUBAO_MODEL`（多模态）。没有独立的 LLM model。

7. **sudo 命令**：任何需要 sudo 的操作不要自动执行（可能卡在密码输入），提示用户手动运行。

8. **Ollama qwen3**：需设置 `OLLAMA_THINK=false` 以保证 tool_calls 输出稳定。

9. **前端无路由/状态管理库**：状态全在 `useSession` hook 里，没有 Redux 或 React Router。

## 环境变量速查

完整列表见 `.env.example`，这里只列最关键的：

| 变量 | 说明 | 默认值 |
|-----|------|-------|
| `ARK_API_KEY` | 火山引擎 ARK API Key | 必填 |
| `DATABASE_URL` | PostgreSQL 连接串 | 必填（生产）/ 空（MemoryStore） |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `MOEBIUS_ENABLED` | 启用本地 GPU inpainting | `false` |
| `LAMA_ENABLED` | 启用 LaMa 物体移除 | `false` |
| `OLLAMA_ENABLED` | 启用本地 LLM | `false` |
| `TEXT_LLM_ORDER` | LLM 候选顺序 | `ollama,doubao` |
| `AGENTIC_EDIT_ENABLED` | 启用多步智能编辑 | `false` |
| `AGENTIC_MODEL` | 规划模型 | `openai:doubao-seed-1-6-250615` |

## 技术栈

| 层 | 技术 | 备注 |
|---|------|-----|
| 后端框架 | FastAPI + uvicorn | 无鉴权，全 CORS |
| 任务队列 | Dramatiq + Redis | Actor 模型，支持重试/退避 |
| 工作流引擎 | LangGraph | StateGraph + 条件边，async streaming |
| LLM SDK | OpenAI SDK (兼容) + aisuite | 统一 ollama/doubao 接口 |
| 图像模型 | Doubao Seedream 5.0 / Moebius / LaMa | 云端 + 本地双模式 |
| 数据库 | PostgreSQL 14+ | psycopg2，无 ORM，手写 SQL |
| 前端 | React 18 + TypeScript + Vite | 零路由/状态库依赖 |
| 包管理 | uv (Python) + npm (前端) | setuptools 构建 |
| Python 版本 | 3.11+ | `.python-version` 管理 |
