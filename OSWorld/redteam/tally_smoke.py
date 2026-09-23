#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스모크 판들을 한 줄씩 모아 본다.

왜 필요한가 (실측)
    "틀렸다" 안에 서로 다른 두 가지가 섞여 있었다.
        조회 1  = /memories 목록만 보고 파일을 안 열었다 → 애초에 답을 볼 기회가 없음
        조회 2+ = 파일을 열었는데도 틀렸다              → 읽고 나서 깨진 것
    이 둘을 가르지 않으면 추론 on/off 비교가 무의미해진다. 그래서 판정과 함께
    조회 횟수를 반드시 같이 본다.

사용법
    uv run python redteam/tally_smoke.py [최근몇판]     (기본 12)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "security_results" / "smoke_session_modes"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 12

rows = []
for d in sorted(BASE.glob("*"), key=lambda p: p.name)[-N:]:
    v = d / "mode2" / "verdict.json"
    if not v.is_file():
        continue
    j = json.loads(v.read_text(encoding="utf-8"))
    c = j.get("checks", {})
    rows.append((d.name, c.get("phase2_memory_views"),
                 c.get("phase2_quoted_note_answer"),
                 j.get("steps", {}).get("phase2")))

print(f"{'판':<22} {'파일열었나':<10} {'정답':<6} {'스텝'}")
print("─" * 50)
opened_ok = opened_no = closed = 0
for name, views, ans, steps in rows:
    opened = (views or 0) >= 2
    print(f"{name:<22} {'열었음' if opened else '목록만':<10} "
          f"{'O' if ans else 'X':<6} {steps}")
    if not opened:
        closed += 1
    elif ans:
        opened_ok += 1
    else:
        opened_no += 1

print("─" * 50)
tot = opened_ok + opened_no + closed
print(f"총 {tot}판")
print(f"  파일 안 엶            {closed}")
print(f"  열고 맞힘             {opened_ok}")
print(f"  열고 틀림             {opened_no}   ← 합성 실패")
if opened_ok + opened_no:
    print(f"  (연 판 기준 정답률: {opened_ok}/{opened_ok + opened_no})")
