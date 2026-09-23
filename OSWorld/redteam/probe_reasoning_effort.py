#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luna(gpt-5.6)의 reasoning_effort 를 우리가 통제할 수 있는가 — API 실측 프로브.

    uv run python redteam/probe_reasoning_effort.py

왜 필요한가
  조건 지문에서 thinking 축이 Haiku=False / Kimi=False / **Luna=None** 으로 남는다.
  Luna 는 추론 모델인데 우리가 켜고 끄는 스위치를 안 걸어놨기 때문이다.
  mm_agents/agent.py 의 gpt 분기는 raw payload POST 라 키 하나만 넣으면 되지만,
  **그 키를 API 가 받는지, 받으면 실제로 추론량이 달라지는지는 찔러봐야 안다.**
  추측으로 코드를 고치면 "넣었는데 무시당하는" 상태를 정렬됐다고 착각하게 된다.

무엇을 재는가
  1) reasoning_effort 없이 1회  → 기본 추론 토큰 수
  2) reasoning_effort="minimal" → 받아주는가 / 추론 토큰이 줄어드는가

비용: 짧은 요청 2회. VM 안 뜬다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL = os.environ.get("PROBE_MODEL", "gpt-5.6-luna")
KEY = os.environ.get("OPENAI_API_KEY")
BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
URL = f"{BASE}/chat/completions" if BASE.endswith("/v1") else f"{BASE}/v1/chat/completions"

PROMPT = "What is 17 * 23? Answer with just the number."


def call(effort=None) -> dict:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_completion_tokens": 2000,
    }
    if effort is not None:
        payload["reasoning_effort"] = effort
    r = requests.post(URL, headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {KEY}"},
                      json=payload, timeout=120)
    return {"status": r.status_code, "body": r.json()}


def report(label, res) -> int:
    """반환: 추론 토큰 수, 또는 -1(값 거부), -2(파라미터 자체 미지원/기타 오류).

    ★ 값 거부와 파라미터 미지원을 **반드시 구분한다** (실측 사고).
      처음 판본은 non-200 을 전부 '파라미터 거부'로 뭉갰다. 실제 응답은
      code=unsupported_value / param=reasoning_effort 였고, 이건 파라미터는
      지원되는데 **값만 틀렸다**는 뜻이다. 그걸 '통제 불가'로 읽으면 쓸 수 있는
      스위치를 없다고 결론내게 된다.
    """
    print(f"\n── {label} ──")
    print(f"  HTTP {res['status']}")
    b = res["body"]
    if res["status"] != 200:
        err = (b.get("error") or {})
        code, param = err.get("code"), err.get("param")
        print(f"    code   : {code}")
        print(f"    param  : {param}")
        print(f"    message: {err.get('message')}")
        if code == "unsupported_value" and param == "reasoning_effort":
            print("  △ 파라미터는 지원됨 — 값만 틀림")
            return -1
        print("  ✗ 파라미터 자체가 안 먹거나 다른 오류")
        return -2
    u = b.get("usage") or {}
    det = u.get("completion_tokens_details") or {}
    rt = det.get("reasoning_tokens")
    try:
        content = b["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        content = "(없음)"
    print(f"  ✓ 수락됨")
    print(f"    답변          : {str(content)[:60]!r}")
    print(f"    completion_tok: {u.get('completion_tokens')}")
    print(f"    reasoning_tok : {rt}")
    return rt if isinstance(rt, int) else -2


def main() -> int:
    if not KEY:
        sys.exit("✗ OPENAI_API_KEY 없음 (.env 확인)")
    print(f"모델: {MODEL}\nURL : {URL}")

    base = report("① reasoning_effort 미지정 (현재 우리 상태)", call())
    none = report('② reasoning_effort="none"  ← 끌 수 있는가', call("none"))
    high = report('③ reasoning_effort="high"  ← 정말 먹히는가(대조)', call("high"))

    print("\n" + "═" * 60)
    if none == -2:
        print("판정: 파라미터 자체가 안 먹는다 → Luna 추론 통제 불가.")
        print("  thinking 축은 구조적 잔차로 내리고 '동작이 실제로 다른 교란변수'로 명시.")
        return 1
    if none == -1:
        print("판정: 'none' 도 값 거부 — 위 message 의 지원 목록을 보고 다시 시도할 것.")
        return 1
    print(f"판정: 통제 가능. 추론 토큰  미지정={base}  none={none}  high={high}")
    if none == 0:
        print("  → 'none' 이 추론을 실제로 0 으로 만든다.")
        print("     Haiku(thinking 없음)·Kimi(thinking=False) 와 같은 기준선에 세울 수 있다.")
    if isinstance(high, int) and isinstance(none, int) and high > none:
        print(f"  → high({high}) > none({none}) — 값이 실제로 반영된다('받는 척'이 아님).")
    elif isinstance(high, int) and high == none:
        print("  ⚠ high 와 none 이 같다 — 이 프롬프트가 너무 쉬워서 차이가 안 드러난다.")
        print("     더 어려운 프롬프트로 다시 잴 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
