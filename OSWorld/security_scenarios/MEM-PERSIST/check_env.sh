#!/usr/bin/env bash
# MEM-PERSIST — 실제 점검 로직은 check_env.py 에 있다(OS 무관, 표준 라이브러리만 사용).
# Windows 는 그냥:  python check_env.py
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/check_env.py" "$@"
