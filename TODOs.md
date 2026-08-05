# TODOs — 生产环境升级

## P0 必须做

- [x] **Postgres 存储** — 将 `storage.py` 中的 `MemoryStore` 替换为 Postgres 实现：
  - `users`, `projects`, `sessions`, `turns`, `images`, `jobs` 表
  - 版本树查询（`parent_turn_id` 链表、分支遍历）
  - 事务保证 `turn` 写入与 `session.current_turn_id` 更新原子性
- [x] **对象存储** — `DoubaoImageTool._download()` 本地保存逻辑替换为 S3 / R2 / OSS：
  - 原图、结果图、mask、参考图上传
  - 缩略图生成
  - 临时鉴权 URL
- [x] **异步 Job Queue** — `/execute` 改为异步：
  - Redis Queue / Celery / Dramatiq
  - 任务状态机：`queued → running → qa_checking → retrying → succeeded/failed/cancelled`
  - Worker 进程消费队列，执行 LangGraph workflow
  - 前端轮询或 WebSocket 推送结果

### 功能验证清单（多轮修改 + 版本树）

> 每次改动后手动跑一轮，或用脚本自动化。核心验证 4 条链路：

- [ ] **链路 1：文生图（首轮）**
  - `POST /projects/default/sessions` → 拿到 `session_id`
  - `POST /sessions/{id}/execute {"instruction":"生成一张赛博朋克猫的海报"}` → 返回 `output_image_url`、`intent=generate_image`
  - `GET /sessions/{id}` → `turns` 数组有 1 条记录，`current_turn_id` 指向它
- [ ] **链路 2：图生图（多轮编辑）**
  - `POST /sessions/{id}/execute {"instruction":"把猫变成橙色"}` → 新 `output_image_url`，且图片应保留上轮构图+新颜色
  - `GET /sessions/{id}` → `turns` 有 2 条，第 2 条的 `parent_turn_id` 指向第 1 条
- [ ] **链路 3：版本分支（fork）**
  - `POST /sessions/{id}/switch-current-turn {"turn_id":"turn_1"}` → 切回首轮
  - `POST /sessions/{id}/execute {"instruction":"把猫变成蓝猫"}` → 从 turn_1 fork 出新分支
  - `GET /sessions/{id}` → turns 有 3 条，turn_3 `parent_turn_id=turn_1`（而非 turn_2）
- [ ] **链路 4：undo / redo**
  - `POST /sessions/{id}/undo` → `current_turn_id` 回退到父轮
  - `POST /sessions/{id}/redo` → `current_turn_id` 前进
  - 检查 `GET /sessions/{id}` 中的 `current_turn_id` 变化

### P0 实施拆解（字段与接口平移）

- [x] **Step 1: 固化数据表结构（Postgres）**
  - 新增/对齐表：`sessions`, `turns`, `images`, `jobs`, `model_calls`
  - `turns` 必含：`parent_turn_id`, `input_image_id`, `output_image_id`, `mask_image_id`, `reference_image_ids`, `selected_tool`, `model_provider`, `model_name`, `model_params`, `qa_result`
  - `sessions` 增加版本指针字段（至少 `current_turn_id`，以及 redo 所需结构）
- [x] **Step 2: Repository 层替换 `MemoryStore`**
  - 保持现有方法签名兼容：`create_turn/update_turn/get_turn/get_session/undo/redo/switch_current_turn/record_model_call`
  - 关键写路径加事务：`turn` 更新 + `session.current_turn_id` 更新原子提交
- [x] **Step 3: 资产存储迁移到 S3/OSS**
  - `save_image` 改为保存对象存储 URL 和元数据，不再依赖本地 `output/`
  - `mask`、`result`、`reference` 统一资产类型与 metadata
- [x] **Step 4: `/execute` 改成真正异步任务**
  - API 仅创建 `job + pending turn` 并入队，立即返回 `job_id/turn_id`
  - Worker 拉取任务后调用 `run_workflow`，完成后写回 `jobs/turns/sessions`
  - 补齐取消、超时、重试、失败回写逻辑
- [x] **Step 5: 接口兼容与验收**
  - 保持可用接口：`/turns/{id}`, `/sessions/{id}`, `/undo`, `/redo`, `/switch-current-turn`, `/replay`, `/model-calls`
  - 增加最小回归用例：追踪、回放、回退、可观测 四条主链路

## 用户体验缺陷（会让用户出问题或不方便）

### A. 会直接出问题（数据丢失 / 正确性 bug）

- [x] **刷新页面丢失所有历史（最严重）** — `frontend/src/hooks/useSession.ts` 每次挂载都 `createSession` 新建 session，session_id 既不存 localStorage 也不进 URL；叠加后端 `MemoryStore` 内存存储，用户刷新浏览器或后端重启即丢失全部编辑历史与版本树。
  - 修法：session_id 持久化到 localStorage / URL，挂载时优先复用；后端存储落库（见 P0 Postgres）
- [x] **Redo 按钮判断错误，点了没反应** — `App.tsx` `canRedo = !!currentTurnId`，但真正 redo 依赖后端 `redo_stack`（`storage.py` redo）。redo_stack 为空时按钮仍可点，返回当前 turn 不变，表现为失灵；`switch_current_turn` 清空 redo_stack，fork 分支后 redo 行为不可预期。
  - 修法：`GET /sessions/{id}` 返回 `can_redo`（redo_stack 是否非空），前端据此置灰
- [x] **同步阻塞 + 无超时 / 无取消** — `/execute` 同步执行（`api.py`），出图数秒~数十秒，前端只显示"处理中…"，不能取消、无进度；HTTP 超时后前端报错但后端仍在跑，job 状态无从查询（`/jobs/{id}` 端点存在但前端从不轮询）。
  - 修法：改异步 Job + 前端轮询/WebSocket（见 P0 Job Queue），补充取消与进度
- [x] **错误信息是英文原始异常** — safety_check 返回 `instruction blocked by safety check: xxx`（`workflow.py`）；API key 缺失/网络错误直接把 `str(e)` 抛给用户（`api.py` execute_turn）。用户看到技术堆栈式文本。
  - 修法：错误码 + 中文用户提示映射层，敏感词/安全拦截给友好文案

### B. 基础体验缺失（不方便）

- [x] **无法下载 / 保存结果图** — `ImageViewer.tsx` 没有下载按钮，用户只能右键另存
- [x] **图片无法放大查看** — 生成 2K/4K 图却挤在小面板，无 zoom/pan/全屏，无输入/输出滑动对比
- [x] **前端不支持 mask 局部编辑和参考图** — 后端 `mask_image_id` / `reference_image_ids` / `inpaint` 已就绪（`doubao_image.py`, `tools/mask.py`），但 `InstructionInput` 只能传一张起始图（与 P2「前端本地 mask 圈选」重复，此处强调后端已具备能力）
- [x] **失败后无"重试"按钮** — 后端 `/replay` 已就绪（`api.py`），前端 timeline 只显示 failed（`TurnTimeline.tsx`），用户需手动重打指令
- [ ] **无用户 / 鉴权 / 配额** — user_id 硬编码 `"default"`（`api.py`），多人共享命名空间，付费模型无限调用（与 P2「用户鉴权与配额」呼应）

> **建议优先级**：先补 A-1（session 持久化，防数据丢失）与 B-1/B-2（下载 + 放大，修图工具最基本诉求）。

## P1 尽快做

- [ ] **模型路由升级** — 从硬编码规则改为动态路由，考虑成本、延迟、历史成功率、用户等级
- [ ] **Fallback 机制** — 供应商故障时自动切换 fallback_tool
- [ ] **Observability** — 每轮记录 `latency_ms`, `cost`, `qa_score`, `retry_count`, `error_code` 到日志/监控

## 设计决策（非目标，勿反复提出）

- **不引入独立 Visual QA / VLM 图像评估** — seedream 5.0 本身是多模态模型，生成时已内建质量把控，等价于「多模态大模型兜底」。`agents/visual_qa.py` 保留 `passed=True` 的直通节点只是为了维持 workflow 结构，不是待补的功能缺口。除非出现明确的质量问题数据，否则**不再将「接入真实 Visual QA」列为 TODO**。此决策与 AGENTS.md「seedream 多模态，无需额外 LLM 做意图识别 / prompt 改写 / 路由」一致。

## P2 产品化

- [ ] **CDN 分离部署** — 当前 `api.py` 末尾通过 `app.mount("/", StaticFiles)` 将前端构建产物挂载到后端同域名同端口：
  - **优点**：部署简单（一个进程）、无跨域问题、适合早期/小团队；模型推理是秒级瓶颈，HTTP 毫秒级往返开销可忽略
  - **局限**：静态资源无法上 CDN 加速、前后端不能独立扩容
  - **迁移路径**：删除 `app.mount` 三行 → 前端上 CDN/独立部署 → nginx 反向代理，切换成本很低
- [ ] 用户鉴权与配额
- [ ] 前端版本树展示、对比、分支
- [ ] 前端本地 mask 圈选
- [ ] **分享（分享给朋友 / 社交平台）** — 当前无此功能，结果图只能「下载」后手动转发：
  - **依赖 P0 对象存储** — 结果图 URL 现为火山引擎 CDN 远程 URL（带时效/鉴权）或上传图的 `data:` base64，都不适合直接分享；需先落 S3/OSS 拿到稳定公开链接
  - 只读分享页 + 短链 `/s/{token}`（无需登录查看单图或某个 session）
  - Web Share API（移动端一键调起系统分享）+ 各社交平台分享链接
  - 可选：生成带水印的分享卡片
  - MVP（不依赖对象存储）：Web Share API + 复制图片 / 下载，先满足最基本诉求
- [ ] 模板工作流
- [ ] **批量生成（批量修改多张图）** — 当前完全不支持：`/upload` 只收单文件、`/execute` 一次只处理一条指令+一张当前图且**同步执行**。
  - **最大拦路虎 = 依赖 P0 异步 Job Queue** — 批量 N 张 = N × 数秒~数十秒，同步请求必撞超时、不能取消/看进度/拿部分结果。需 fan-out 成 N 个子任务 + 各自状态机 + 并发上限（防 429）+ 单张重试
  - **数据模型不匹配** — 现在 session 是单指针线性版本树（`current_turn_id` + `parent_turn_id` 链），批量 N 个输出塞不进"单一当前图"；需新增 batch 实体、N 条独立血缘，并定义 undo/redo、"选哪张继续编辑"的语义
  - **存储与成本** — N 张结果图仍走本地/临时 CDN URL（依赖 P0 对象存储），且付费模型 N 倍调用需配合鉴权/配额（user_id 现硬编码 `default`）
  - 结论：UI/循环是小事，**不先做 P0 异步化，批量做出来也不可用**
  - **分阶段实施路径（B 先行 → A 扩展）**：
    - **阶段 1 — 模式 B：一图 → 多变体/多规格（MVP 首选，性价比最高）**
      - 场景：多平台/多尺寸适配（1:1 / 9:16 / 16:9）、A/B 变体比选、同图多风格探索
      - 数据模型改动小：单一输入 fan-out 成 N 个子任务（不同 seed / size / prompt 变体），共享同一 parent turn
      - 目的：先用简单场景**打通并验证异步 Job Queue 链路**（fan-out + 进度 + 部分结果 + 单个重试），再谈复杂批量
    - **阶段 2 — 模式 A：多图 → 同一操作（需求最刚需，量最大）**
      - 场景：电商商品图批量换背景/统一风格/加水印、摄影批量调色、房产批量 staging
      - 依赖阶段 1 的异步基建，额外需：**多图上传**（`/upload` 支持多文件）+ **每张图独立血缘**（batch 实体 + N 条 turn 链）+ 配额/鉴权
    - **阶段 3（可选）— 模式 C：多图各自不同操作** — 偏"模板工作流/流水线"，与「模板工作流」条目合并考虑
- [ ] 用户反馈闭环
