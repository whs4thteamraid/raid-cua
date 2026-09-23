#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luna(gpt-5.6)가 temperature 0.6 을 받는가 — 실측 프로브.

    uv run python redteam/probe_luna_temperature.py

왜 필요한가 (실측)
  Kimi 는 추론을 끄면(thinking={"type":"disabled"}) temperature 를 **0.6 으로 강제**한다.
  지금 세 모델은 1.0 으로 맞춰져 있으므로, Kimi 추론을 끄는 순간 temperature 축이 깨진다.
  셋 다 0.6 으로 갈 수 있으면 thinking 과 temperature 를 **동시에** 맞출 수 있다.
  Claude 는 0~1 아무 값이나 받지만 gpt-5.6 은 모른다 → 찔러본다.
"""
from __future__ import annotations

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


def call(temp, effort="none"):
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": "What is 17 * 23? Answer with just the number."}],
               "max_completion_tokens": 2000, "reasoning_effort": effort}
    if temp is not None:
        payload["temperature"] = temp
    r = requests.post(URL, headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {KEY}"},
                      json=payload, timeout=120)
    return r.status_code, r.json()


def main() -> int:
    if not KEY:
        sys.exit("✗ OPENAI_API_KEY 없음 (.env 확인)")
    print(f"모델: {MODEL}  (reasoning_effort='none' 고정)\n")
    ok = {}
    for temp in (1.0, 0.6, None):
        label = "미전송" if temp is None else str(temp)
        st, b = call(temp)
        print(f"── temperature={label} ──")
        print(f"  HTTP {st}")
        if st != 200:
            err = b.get("error") or {}
            print(f"  ✗ {err.get('code')} / {err.get('param')}: {err.get('message')}")
            ok[label] = False
        else:
            u = b.get("usage") or {}
            det = u.get("completion_tokens_details") or {}
            print(f"  ✓ 수락  답변={b['choices'][0]['message']['content']!r}"
                  f"  reasoning_tok={det.get('reasoning_tokens')}")
            ok[label] = True
        print()

    print("═" * 60)
    if ok.get("0.6"):
        print("판정: Luna 가 0.6 을 받는다.")
        print("  → 세 모델 모두 temperature 0.6 + 확장추론 OFF 로 갈 수 있다.")
        print("     thinking 과 temperature 를 **동시에** 맞출 수 있다.")
        return 0
    print("판정: Luna 가 0.6 을 거부한다 (위 message 확인).")
    print("  → thinking 과 temperature 를 동시에 맞출 수 없다. 둘 중 하나를 택하고")
    print("     나머지를 구조적 잔차로 기록해야 한다.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
