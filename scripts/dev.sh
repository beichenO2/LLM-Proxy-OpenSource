#!/usr/bin/env bash
# 本地开发：后端 12790 + 前端 5170
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== LLM Proxy 开发启动 ==="
echo "后端: http://127.0.0.1:12790"
echo "前端: http://127.0.0.1:5170"
echo ""

if ! command -v privportal >/dev/null 2>&1; then
  echo "请先安装后端: cd backend && pip install -e .  （或 uv sync）"
  exit 1
fi

cd "$ROOT/backend"
if [[ ! -f privportal.db ]]; then
  echo "[init] privportal init-db"
  privportal init-db
fi

privportal start &
BACK_PID=$!
trap 'kill $BACK_PID 2>/dev/null || true' EXIT

sleep 1
cd "$ROOT/frontend"
npm run dev
