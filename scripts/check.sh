#!/usr/bin/env bash
# 插件检查：ruff + pytest，都在 astrbot 容器里跑（宿主机没有依赖）。
# 用法：scripts/check.sh [pytest 参数...]
set -euo pipefail

plugin=/AstrBot/data/plugins/astrbot_plugin_md_render

if [ "$(docker inspect -f '{{.State.Running}}' astrbot 2>/dev/null)" != "true" ]; then
  echo "astrbot 容器没在跑，检查无法执行：docker compose -f services/astrbot/docker-compose.yml up -d" >&2
  exit 1
fi

docker exec -w "$plugin" astrbot ruff check .
docker exec -w "$plugin" astrbot python3 -m pytest -q "$@"
