#!/usr/bin/env bash
# 后端本地启动：自检 -> 幂等初始化 -> 起 uvicorn。
# 自检不过直接退出：退出码 2 = 依赖没装好，3 = 初始化数据缺失，4 = 防雷元件样例不全。
# 运行日志固定写到 backend/logs/backend.log（同时输出到终端）。
set -euo pipefail
cd "$(dirname "$0")"

APP_ENV="${APP_ENV:-local}"
export APP_ENV
APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8000}"
LOG_DIR="${LOG_DIR:-$PWD/logs}"

PYTHON=".venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "[run.sh] 未找到虚拟环境，先创建 .venv 并安装依赖 ..."
  if ! python3 -m venv .venv; then
    cat >&2 <<'EOF'
[run.sh] 创建虚拟环境失败：当前 Python 缺少 venv 模块。
Debian/Ubuntu 请先执行：sudo apt install python3-venv（或 python3.11-venv），
然后重新运行 ./run.sh。
EOF
    exit 2
  fi
fi

.venv/bin/pip install -q -r requirements.txt

echo "[run.sh] 启动前自检与幂等初始化 ..."
set +e
"$PYTHON" -m app.bootstrap init
code=$?
set -e
if [ "$code" -ne 0 ]; then
  echo "[run.sh] 自检未通过（退出码 $code），服务不启动。"
  case "$code" in
    2) echo "[run.sh] → 依赖没装好：见上方 FAIL 项，重新执行 .venv/bin/pip install -r requirements.txt" ;;
    3) echo "[run.sh] → 初始化数据缺失或损坏：确认 backend/data/seed.json 存在且是合法 JSON" ;;
    4) echo "[run.sh] → 防雷元件样例不全：seed.json 需覆盖泄露超标 / 动作频繁 / 已更换三种情形" ;;
  esac
  exit "$code"
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backend.log"
echo "[run.sh] 环境=$APP_ENV 监听=$APP_HOST:$APP_PORT 日志=$LOG_FILE"
exec .venv/bin/uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" 2>&1 | tee -a "$LOG_FILE"
