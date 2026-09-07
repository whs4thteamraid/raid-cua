#!/usr/bin/env bash
# MEM-PERSIST — A 조건용 감염 스냅샷 생성.
# 실제 로직은 make_infected_snapshot.py 에 있고, 이 래퍼는 프로젝트 venv(uv)로 실행해 준다.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
[ -f "$ROOT/redteam/run_claude_3.py" ] || { echo "✗ OSWorld 루트를 못 찾음: $ROOT"; exit 1; }
command -v uv >/dev/null || { echo "✗ uv 없음"; exit 1; }
cd "$ROOT"
exec env PYTHONPATH=. uv run python "security_scenarios/MEM-PERSIST/make_infected_snapshot.py" "$@"
