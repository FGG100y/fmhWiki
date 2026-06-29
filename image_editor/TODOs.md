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
