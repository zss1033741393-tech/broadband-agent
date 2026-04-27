#!/usr/bin/env bash
# 自定位到 plugin 根目录，确保 Python 环境就绪。
# 由 hooks.json 在 session_start 时调用。
set -uo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PLUGIN_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "[fae-plugin] WARN: uv not found in PATH, skipping dependency sync" >&2
  exit 0
fi

uv sync --quiet 2>&1 || {
  echo "[fae-plugin] WARN: uv sync failed (non-fatal); plugin scripts may not run until deps are installed" >&2
  exit 0
}
