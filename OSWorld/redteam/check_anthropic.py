#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Computer Use '구성 확인' 스크립트 — VM/OSWorld 없이, API 키·모델·베타가
실제로 통하는지만 5초 안에 검증한다. 패치 전에 이걸 먼저 통과시켜 두면
"config 문제"와 "배선 문제"를 분리할 수 있다.

사용:
    python3 check_anthropic.py                       # 기본: claude-haiku-4-5
    python3 check_anthropic.py --model claude-opus-4-8
    python3 check_anthropic.py --with-bash           # bash 툴까지 함께 확인(유형2 목표 구성)

읽는 환경변수: ANTHROPIC_API_KEY  (.env 자동 로드)
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# 모델별 computer-use 베타/툴 짝 (agent.py 자동전환과 동일 규칙)
#   - haiku 4.5           → computer_20250124 / beta computer-use-2025-01-24 (구형)
#   - opus 4.6+/sonnet 4.6+ → computer_20251124 / beta computer-use-2025-11-24 (신형)
BASH_TOOL = {"type": "bash_20250124", "name": "bash"}


def pick_config(model: str):
    m = model.lower()
    if "haiku" in m:
        beta = "computer-use-2025-01-24"
        computer = {
            "type": "computer_20250124", "name": "computer",
            "display_width_px": 1280, "display_height_px": 720, "display_number": 1,
        }
    else:
        beta = "computer-use-2025-11-24"
        computer = {
            "type": "computer_20251124", "name": "computer",
            "display_width_px": 1280, "display_height_px": 720, "display_number": 1,
        }
    return beta, computer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="claude-haiku-4-5 / claude-sonnet-4-6+ / claude-opus-4-6~4-8 ...")
    ap.add_argument("--with-bash", action="store_true", help="bash 툴도 tools 배열에 포함")
    args = ap.parse_args()

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("✗ ANTHROPIC_API_KEY 가 없습니다. .env 에 ANTHROPIC_API_KEY=sk-ant-... 추가하세요.")
    print(f"✔ 키 감지됨: {key[:10]}…{key[-4:]}  (len={len(key)})")

    try:
        import anthropic
    except ImportError:
        sys.exit("✗ anthropic 미설치.  pip install anthropic")
    print(f"✔ anthropic SDK {anthropic.__version__}")

    beta, computer_tool = pick_config(args.model)
    tools = [computer_tool] + ([BASH_TOOL] if args.with_bash else [])
    print(f"→ model={args.model}  beta={beta}  tools={[t['name'] for t in tools]}")

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 사용
    try:
        r = client.beta.messages.create(
            model=args.model,
            max_tokens=512,
            tools=tools,
            betas=[beta],
            messages=[{
                "role": "user",
                "content": "In one short sentence, confirm you are running and list the tool "
                           "names you have available. Do not call any tool.",
            }],
        )
    except Exception as e:  # noqa
        name = type(e).__name__
        code = getattr(e, "status_code", None)
        hint = {
            401: "키가 틀렸거나 만료됨.",
            400: "모델명 또는 툴/베타 버전 불일치 가능 → --model 을 확인하세요.",
            404: "그 모델을 계정에서 못 씀 → 다른 모델로.",
            402: "크레딧/결제 필요 → 콘솔 Billing.",
            429: "레이트리밋/크레딧 소진.",
        }.get(code, "")
        sys.exit(f"✗ API 호출 실패 [{name} status={code}] {e}\n  힌트: {hint}")

    text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    print("\n✔ API OK  stop_reason=%s  usage(in/out)=%s/%s" % (
        r.stop_reason, r.usage.input_tokens, r.usage.output_tokens))
    print("  모델 응답:", text.strip()[:400])
    print("\n요약: 인증·모델·베타(+bash 툴) 구성이 정상입니다. 이제 OSWorld 배선(패치)로 넘어가면 됩니다.")


if __name__ == "__main__":
    main()
