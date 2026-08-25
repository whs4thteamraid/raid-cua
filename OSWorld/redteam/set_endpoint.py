#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 서버 주소 한 번에 갱신 — RunPod 팟을 껐다 켜서 URL이 바뀔 때
.env 의 OPENCUA_BASE_URL 을 자동으로 고쳐 준다. (연결 확인 덤)

이 파일은 OSWorld-audit 루트에 둔다 (.env 와 같은 폴더).

사용:
    python3 set_endpoint.py https://xxxx-8000.proxy.runpod.net
    python3 set_endpoint.py xxxx                 # pod id만 → https://xxxx-8000.proxy.runpod.net
    python3 set_endpoint.py https://... --model opencua-72b
    python3 set_endpoint.py --show               # 현재 .env 값 보기
    python3 set_endpoint.py https://... --no-check   # 연결 확인 생략
"""
from __future__ import annotations

import argparse
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# .env lives at the repo root; find it robustly whether this script is at root or in redteam/.
_ROOT = next((p for p in Path(__file__).resolve().parents if (p / "desktop_env").is_dir()), HERE)
ENV = _ROOT / ".env"


def build_url(arg: str, port: int) -> str:
    a = arg.strip().rstrip("/")
    if a.startswith(("http://", "https://")):
        return a
    return f"https://{a}-{port}.proxy.runpod.net"   # pod id만 준 경우


def read_env() -> list[str]:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.is_file() else []


def set_key(lines: list[str], key: str, value: str) -> list[str]:
    out, found = [], False
    for ln in lines:
        if re.match(rf"\s*{re.escape(key)}\s*=", ln):   # 주석(#로 시작)은 안 건드림
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    return out


def get_key(lines: list[str], key: str):
    for ln in lines:
        m = re.match(rf"\s*{re.escape(key)}\s*=\s*(.*)", ln)
        if m:
            return m.group(1).strip()
    return None


def check(url: str):
    """OpenCUA(vLLM) 엔드포인트가 응답하는지 가볍게 확인."""
    last = "no response"
    for path in ("/v1/models", "/health", "/"):
        try:
            req = urllib.request.Request(url.rstrip("/") + path, method="GET")
            with urllib.request.urlopen(req, timeout=6) as r:
                return True, f"{path} → HTTP {r.status}"
        except Exception as e:
            last = f"{path} → {type(e).__name__}"
    return False, last


def main() -> None:
    ap = argparse.ArgumentParser(description="RunPod LLM 엔드포인트 갱신기")
    ap.add_argument("endpoint", nargs="?", help="RunPod URL 또는 pod id")
    ap.add_argument("--model", help="OPENCUA_MODEL 도 함께 설정")
    ap.add_argument("--port", type=int, default=8000, help="pod id만 줄 때 붙일 포트(기본 8000)")
    ap.add_argument("--show", action="store_true", help="현재 .env 값만 출력")
    ap.add_argument("--no-check", action="store_true", help="연결 확인 생략")
    args = ap.parse_args()

    lines = read_env()

    if args.show or not args.endpoint:
        print(f".env: {ENV}")
        print(f"  OPENCUA_BASE_URL = {get_key(lines, 'OPENCUA_BASE_URL')}")
        print(f"  OPENCUA_MODEL    = {get_key(lines, 'OPENCUA_MODEL')}")
        if not args.endpoint and not args.show:
            print("\n사용: python3 set_endpoint.py <RunPod URL 또는 pod id> [--model ...]")
        return

    url = build_url(args.endpoint, args.port)
    lines = set_key(lines, "OPENCUA_BASE_URL", url)
    if args.model:
        lines = set_key(lines, "OPENCUA_MODEL", args.model)
    ENV.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")

    print(f"✔ OPENCUA_BASE_URL = {url}")
    if args.model:
        print(f"✔ OPENCUA_MODEL    = {args.model}")

    if not args.no_check:
        ok, msg = check(url)
        print(("✔ 연결 OK: " if ok else "⚠ 연결 안 됨(팟이 아직 부팅 중일 수 있음): ") + msg)

    print("\n※ 지금 터미널에 OPENCUA_BASE_URL 이 export 돼 있으면 .env 가 무시됩니다.")
    print("  새 터미널을 열거나  unset OPENCUA_BASE_URL  후 실행하세요.")


if __name__ == "__main__":
    main()
