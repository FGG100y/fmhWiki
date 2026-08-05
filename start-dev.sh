#!/usr/bin/env bash
# 一条命令同时启动：后端 API(8000) + Worker + 前端开发服务器(5173)
# 用法：./start-dev.sh        （Ctrl+C 停止全部服务）
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 解析 Python：默认用 uv（仓库根 .python-version / uv.lock），可用 PYTHON_BIN 覆盖为具体解释器 ──
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PY() { "$PYTHON_BIN" "$@"; }
else
  PY() { uv run "$@"; }
fi

# ── 校验 uv / npm ──
if [[ -z "${PYTHON_BIN:-}" ]] && ! command -v uv >/dev/null 2>&1; then
  echo "错误：未找到 uv，请先安装 https://docs.astral.sh/uv/" >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "错误：未找到 npm，请先安装 Node.js" >&2
  exit 1
fi

PIDS=()

cleanup() {
  echo ""
  echo "正在停止全部服务…"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  echo "已全部停止。"
}
trap cleanup INT TERM EXIT

# 后端（worker 必须 --processes 1 --threads 2，防止多进程各自加载模型导致 OOM）
PY python -m painterAgent.main &
PIDS+=("$!")

PY python -m dramatiq painterAgent.worker --processes 1 --threads 2 &
PIDS+=("$!")

( cd "$ROOT/frontend" && npm run dev ) &
PIDS+=("$!")

echo "服务启动中："
echo "  后端   → http://localhost:8000"
echo "  Worker → 图片生成队列"
echo "  前端   → http://localhost:5173"
echo "按 Ctrl+C 停止全部服务。"

wait
