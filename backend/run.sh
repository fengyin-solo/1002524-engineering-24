#!/usr/bin/env bash
# 后端启动脚本：一次装好依赖并启动，日志同时输出到终端与 logs/backend.log。
# 换机器后若旧 venv 失效（解释器路径不存在，例如在别的系统上创建的），会自动重建。
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="logs"
LOG_FILE="${APP_LOG_PATH:-$LOG_DIR/backend.log}"
HOST="${APP_HOST:-127.0.0.1}"
PORT="${APP_PORT:-8000}"
INSTALL_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --install-only) INSTALL_ONLY=1 ;;
    *) echo "[run.sh] 未知参数：$arg" >&2; exit 2 ;;
  esac
done

# 1. 准备一个可用的 venv
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "[run.sh] 未发现可用虚拟环境，开始创建 .venv ..."
  rm -rf .venv
  if "$PYTHON_BIN" -m venv .venv >/dev/null 2>&1; then
    :
  elif "$PYTHON_BIN" -m virtualenv .venv >/dev/null 2>&1; then
    :
  else
    echo "[run.sh] 创建虚拟环境失败：请先安装 python3-venv，或执行 'pip install --user virtualenv' 后重试" >&2
    exit 1
  fi
fi

# 2. 按锁定版本安装依赖（已装齐时很快）
.venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

if [ "$INSTALL_ONLY" -eq 1 ]; then
  echo "[run.sh] 依赖已按 requirements.txt 安装完成"
  exit 0
fi

# 3. 启动并落日志（Ctrl-C 经 wait 正常传递给 uvicorn）
mkdir -p "$LOG_DIR"
echo "[run.sh] 启动后端：http://$HOST:$PORT （日志：$LOG_FILE）"
set -o pipefail
.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" 2>&1 | tee -a "$LOG_FILE" &
CHILD=$!
trap 'kill "$CHILD" 2>/dev/null || true' INT TERM
wait "$CHILD"
