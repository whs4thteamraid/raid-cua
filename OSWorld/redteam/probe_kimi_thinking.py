#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kimi(k2.6)의 네이티브 추론을 API 수준에서 끌 수 있는가 — 실측 프로브.

    uv run python redteam/probe_kimi_thinking.py

왜 필요한가 (실측)
  KimiAgent 의 `thinking` 인자는 **시스템 프롬프트와 파서만** 바꾼다. payload 에는
  추론 제어 파라미터가 없고, thinking=False 로 둬도 API 는 reasoning_content 를
  계속 채워 보낸다(스모크 실측: ON 2819자 / OFF 1914자 — 줄기만 하고 0 이 아니다).
  그래서 그 플래그를 "추론 껐음" 으로 기록하면 거짓 정렬이 된다.

  Haiku 는 thinking 파라미터 미전송으로, Luna 는 reasoning_effort="none" 으로
  실제 0 을 만들었다. Kimi 에도 그런 스위치가 있는지 **찔러봐야** 안다.
  없으면 없다는 것이 결론이고, thinking 축은 잔차로 내려야 한다.

비용: 짧은 요청 여러 번. VM 안 뜬다.
"""
from __future__ import annotations

import json
import os
import re
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

# 후보 — 벤더마다 이름이 다르므로 대표적인 것들을 훑는다.
CANDIDATES = [
    ("기준선 (아무것도 안 보냄)", {}),
    ("enable_thinking=False", {"enable_thinking": False}),
    ("thinking=False", {"thinking": False}),
    ('thinking={"type":"disabled"}', {"thinking": {"type": "disabled"}}),
    ('reasoning_effort="none"', {"reasoning_effort": "none"}),
    ('chat_template_kwargs', {"chat_template_kwargs": {"enable_thinking": False}}),
]


ONLY_RE = re.compile(r"only ([0-9.]+) is allowed", re.I)


def call(extra: dict, temperature: float = 1.0) -> dict:
    payload = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
               "max_tokens": 2000, "temperature": temperature, "top_p": 0.95}
    payload.update(extra)
    r = requests.post(URL, headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {KEY}"},
                      json=payload, timeout=120)
    return {"status": r.status_code, "body": r.json(), "temperature": temperature}


def call_adaptive(extra: dict) -> dict:
    """거부 사유가 '다른 값만 허용' 이면 그 값으로 **한 번 다시** 시도한다.

    ★ 왜 (실측 사고) — 처음 판본은 non-200 을 전부 '파라미터 거부'로 뭉갰다. 실제로는
      thinking={"type":"disabled"} 가 thinking 검증을 통과하고 **temperature 에서** 걸렸고
      (`invalid temperature: only 0.6 is allowed`), 그걸 '스위치 없음' 으로 결론냈다.
      에러가 알려주는 제약을 읽고 따라가야 무엇이 지원되는지가 드러난다.
    """
    res = call(extra)
    if res["status"] == 200:
        return res
    msg = str(((res["body"].get("error") or {}).get("message")) or "")
    m = ONLY_RE.search(msg)
    if m and "temperature" in msg.lower():
        t = float(m.group(1))
        print(f"    ↻ temperature {t} 로 재시도 (에러가 지정한 값)")
        return call(extra, temperature=t)
    return res


def main() -> int:
    if not KEY:
        sys.exit("✗ KIMI_API_KEY 없음 (.env 확인)")
    print(f"모델: {MODEL}\nURL : {URL}")
    results = []
    for label, extra in CANDIDATES:
        print(f"\n── {label} ──")
        res = call_adaptive(extra)
        print(f"  HTTP {res['status']}  (temperature={res['temperature']})")
        b = res["body"]
        if res["status"] != 200:
            err = (b.get("error") or {})
            print(f"  ✗ {err.get('type')}: {err.get('message')}")
            results.append((label, None))
            continue
        try:
            msg = b["choices"][0]["message"]
        except (KeyError, IndexError):
            print(f"  ? 예상 못한 응답: {json.dumps(b)[:200]}")
            results.append((label, None))
            continue
        rc = str(msg.get("reasoning_content") or "")
        print(f"  ✓ 수락됨")
        print(f"    답변              : {str(msg.get('content'))[:40]!r}")
        print(f"    reasoning_content : {len(rc)}자")
        results.append((label, len(rc)))

    print("\n" + "═" * 60)
    base = results[0][1]
    zeros = [(l, n) for l, n in results[1:] if n == 0]
    if zeros:
        print("판정: 추론을 끌 수 있다 ↓")
        for l, _ in zeros:
            print(f"  → {l}")
        print("  이 파라미터를 kimi_agent payload 에 넣으면 thinking 축을 맞출 수 있다.")
        return 0
    accepted = [(l, n) for l, n in results[1:] if n is not None]
    print(f"판정: 추론을 끄는 스위치를 못 찾았다. (기준선 {base}자)")
    if accepted:
        print("  수락은 됐지만 추론이 안 줄어든 것들 — '받는 척' 일 뿐:")
        for l, n in accepted:
            print(f"    {l}: {n}자")
    print("  → thinking 축은 구조적 잔차. 'Kimi 만 확장 추론이 통제되지 않는다' 를")
    print("     교란변수로 명시하고, native_reasoning_chars 로 매 판 기록할 것.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
