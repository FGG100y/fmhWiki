# TODOs — 生产环境升级

## P0 必须做

- [ ] **Postgres 存储** — 将 `storage.py` 中的 `MemoryStore` 替换为 Postgres 实现：
  - `users`, `projects`, `sessions`, `turns`, `images`, `jobs` 表
  - 版本树查询（`parent_turn_id` 链表、分支遍历）
  - 事务保证 `turn` 写入与 `session.current_turn_id` 更新原子性
- [ ] **对象存储** — `DoubaoImageTool._download()` 本地保存逻辑替换为 S3 / R2 / OSS：
  - 原图、结果图、mask、参考图上传
  - 缩略图生成
  - 临时鉴权 URL
- [ ] **异步 Job Queue** — `/execute` 改为异步：
  - Redis Queue / Celery / Dramatiq
  - 任务状态机：`queued → running → qa_checking → retrying → succeeded/failed/cancelled`
  - Worker 进程消费队列，执行 LangGraph workflow
  - 前端轮询或 WebSocket 推送结果

### P0 实施拆解（字段与接口平移）

- [ ] **Step 1: 固化数据表结构（Postgres）**
  - 新增/对齐表：`sessions`, `turns`, `images`, `jobs`, `model_calls`
  - `turns` 必含：`parent_turn_id`, `input_image_id`, `output_image_id`, `mask_image_id`, `reference_image_ids`, `selected_tool`, `model_provider`, `model_name`, `model_params`, `qa_result`
  - `sessions` 增加版本指针字段（至少 `current_turn_id`，以及 redo 所需结构）
- [ ] **Step 2: Repository 层替换 `MemoryStore`**
  - 保持现有方法签名兼容：`create_turn/update_turn/get_turn/get_session/undo/redo/switch_current_turn/record_model_call`
  - 关键写路径加事务：`turn` 更新 + `session.current_turn_id` 更新原子提交
- [ ] **Step 3: 资产存储迁移到 S3/OSS**
  - `save_image` 改为保存对象存储 URL 和元数据，不再依赖本地 `output/`
  - `mask`、`result`、`reference` 统一资产类型与 metadata
- [ ] **Step 4: `/execute` 改成真正异步任务**
  - API 仅创建 `job + pending turn` 并入队，立即返回 `job_id/turn_id`
  - Worker 拉取任务后调用 `run_workflow`，完成后写回 `jobs/turns/sessions`
  - 补齐取消、超时、重试、失败回写逻辑
- [ ] **Step 5: 接口兼容与验收**
  - 保持可用接口：`/turns/{id}`, `/sessions/{id}`, `/undo`, `/redo`, `/switch-current-turn`, `/replay`, `/model-calls`
  - 增加最小回归用例：追踪、回放、回退、可观测 四条主链路

## P1 尽快做

- [ ] **模型路由升级** — 从硬编码规则改为动态路由，考虑成本、延迟、历史成功率、用户等级
- [ ] **Visual QA 接入真实图像评估** — 当前基于文本推断，应接入 VLM 或专用图像质量模型
- [ ] **Fallback 机制** — 供应商故障时自动切换 fallback_tool
- [ ] **Observability** — 每轮记录 `latency_ms`, `cost`, `qa_score`, `retry_count`, `error_code` 到日志/监控

## P2 产品化

- [ ] 用户鉴权与配额
- [ ] 前端版本树展示、对比、分支
- [ ] 前端本地 mask 圈选
- [ ] 模板工作流
- [ ] 批量生成
- [ ] 用户反馈闭环
