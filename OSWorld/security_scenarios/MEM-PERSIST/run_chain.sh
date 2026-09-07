#!/usr/bin/env bash
# MEM-PERSIST — A 계보 풀체인 실행기 (스냅샷 불필요, 시딩 없음).
#   ./run_chain.sh <faithful|controlled|inject> <cued|benign> [N]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
[ -f "$ROOT/redteam/run_claude_3.py" ] || { echo "✗ OSWorld 루트를 못 찾음: $ROOT"; exit 1; }
command -v uv >/dev/null || { echo "✗ uv 없음"; exit 1; }
cd "$ROOT"
exec env PYTHONPATH=. uv run python "security_scenarios/MEM-PERSIST/run_chain.py" "$@"
