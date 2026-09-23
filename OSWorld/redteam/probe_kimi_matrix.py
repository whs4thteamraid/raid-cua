#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kimi — thinking × temperature 조합 매트릭스 실측.

    uv run python redteam/probe_kimi_matrix.py

왜 필요한가 (실측 사고)
  GUI 40스텝 판에서 Kimi phase2 가 **퇴화 루프**에 빠졌다. step 9~13 의 추론 텍스트가
  글자까지 동일하고, 같은 좌표를 9스텝 연속 클릭했다. 09-14 문서가 경고한
  "thinking 없으면 환각 후 조기 종료" 가 GUI 태스크에서 재현된 것으로 보인다.

  그런데 원인 후보가 둘이고 **서로 묶여 있다**:
    ① 네이티브 추론 OFF   ② temperature 1 → 0.6
  Moonshot 이 thinking={"type":"disabled"} 를 걸면 temperature 0.6 을 강제하므로,
  지금 배선에서는 이 둘을 따로 뗄 수 없다.

  이 프로브가 답할 질문: **추론 ON 을 temperature 0.6 으로 돌릴 수 있는가?**
    - 가능하면 → temperature 를 고정한 채 추론만 바꾼 **깨끗한 대조군**을 돌릴 수 있다.
    - 불가능하면 → 두 변수는 구조적으로 분리 불가. 그 사실 자체를 기록해야 한다.

  ※ 판정은 "수락됐는가" 가 아니라 **reasoning_content 가 실제로 0 인가**로 한다.
    앞선 프로브들에서 수락은 되는데 아무 효과 없는 파라미터를 세 번 만났다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = os.environ.get("PROBE_MODEL", "kimi-k2.6")
KEY = os.environ.get("KIMI_API_KEY")
URL = "https://api.moonshot.ai/v1/chat/completions"
PROMPT = "What is 17 * 23? Answer with just the number."

CASES = [
    ("추론 ON  (thinking 미지정)", None,                      1.0),
    ("추론 ON  (thinking 미지정)", None,                      0.6),
    ("추론 OFF (disabled)",        {"type": "disabled"},      1.0),
    ("추론 OFF (disabled)",        {"type": "disabled"},      0.6),
]


def call(thinking, temp):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
               "max_tokens": 2000, "temperature": temp, "top_p": 0.95}
    if thinking is not None:
        payload["thinking"] = thinking
    r = requests.post(URL, headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {KEY}"},
                      json=payload, timeout=120)
    return r.status_code, r.json()


def main() -> int:
    if not KEY:
        sys.exit("✗ KIMI_API_KEY 없음 (.env 확인)")
    print(f"모델: {MODEL}\n")
    grid = {}
    for label, thinking, temp in CASES:
        st, b = call(thinking, temp)
        key = ("off" if thinking else "on", temp)
        print(f"── {label}  temperature={temp} ──")
        print(f"  HTTP {st}")
        if st != 200:
            err = b.get("error") or {}
            print(f"  ✗ {err.get('type')}: {err.get('message')}")
            grid[key] = None
        else:
            msg = b["choices"][0]["message"]
            rc = str(msg.get("reasoning_content") or "")
            print(f"  ✓ 수락  답변={str(msg.get('content'))[:30]!r}  reasoning={len(rc)}자")
            grid[key] = len(rc)
        print()

    print("═" * 62)
    print(f"{'':10s} {'temp 1.0':>14s} {'temp 0.6':>14s}")
    for mode in ("on", "off"):
        row = []
        for t in (1.0, 0.6):
            v = grid.get((mode, t))
            row.append("거부" if v is None else f"추론 {v}자")
        print(f"  추론 {mode:4s} {row[0]:>14s} {row[1]:>14s}")
    print()

    on06 = grid.get(("on", 0.6))
    if on06 is not None and on06 > 0:
        print("판정: 추론 ON 을 temperature 0.6 에서 돌릴 수 있다.")
        print("  → temperature 를 0.6 으로 **고정한 채** 추론만 켜고 끈 대조군이 가능하다.")
        print("     루프의 원인이 '추론 OFF' 인지 'temperature' 인지 가를 수 있다.")
        return 0
    if on06 is None:
        print("판정: 추론 ON + temperature 0.6 은 **거부된다.**")
    else:
        print("판정: 추론 ON + 0.6 은 수락되지만 추론이 0 이다 — 사실상 OFF.")
    print("  → 두 변수는 구조적으로 분리 불가. 대조군은 (ON,1.0) vs (OFF,0.6) 뿐이고,")
    print("     그 비교에는 temperature 차이가 섞인다는 것을 기록해야 한다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
