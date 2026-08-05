#!/usr/bin/env bash
# 一条命令同时启动：后端 API(8000) + Worker + 前端开发服务器(5173)
# 用法：./start-dev.sh        （Ctrl+C 停止全部服务）
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 解析 Python：优先使用 pyenv 虚拟环境 image-editor ──
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]] && command -v pyenv >/dev/null 2>&1; then
  PYENV_PY="$(pyenv root)/versions/image-editor/bin/python"
  if [[ -x "$PYENV_PY" ]]; then
    PYTHON_BIN="$PYENV_PY"
  fi
fi
PYTHON_BIN="${PYTHON_BIN:-python}"

# ── 校验 npm ──
if ! command -v npm >/dev/null 2>&1; then
  echo "错误：未找到 npm，请先安装 Node.js" >&2
  exit 1
fi

cd "$ROOT/image_editor"

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

echo "使用 Python: $PYTHON_BIN"

# 后端（worker 必须 --processes 1 --threads 2，防止多进程各自加载模型导致 OOM）
"$PYTHON_BIN" -m image_editor.main &
PIDS+=("$!")

"$PYTHON_BIN" -m dramatiq image_editor.worker --processes 1 --threads 2 &
PIDS+=("$!")

( cd "$ROOT/image_editor/frontend" && npm run dev ) &
PIDS+=("$!")

echo "服务启动中："
echo "  后端   → http://localhost:8000"
echo "  Worker → 图片生成队列"
echo "  前端   → http://localhost:5173"
echo "按 Ctrl+C 停止全部服务。"

wait
