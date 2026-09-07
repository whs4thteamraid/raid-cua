#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEM-PERSIST — 현재 호스트 IP 를 시나리오 JSON 에 동기화한다 (OS 무관).

VM 은 /etc/hosts 로 mirror.raid.internal · pkg-telemetry-cdn.net 을 호스트 IP 로
보내는데, 그 IP 가 시나리오 JSON 안에 박혀 있다. Wi-Fi 가 바뀌면 한 번 실행한다.

    python sync_ip.py            # 감지된 IP 로 동기화
    python sync_ip.py 192.168.0.7   # IP 직접 지정
"""
from __future__ import annotations
import re, socket, sys
from pathlib import Path

# 출력을 파일·파이프로 돌렸을 때 Windows(cp949)가 '✔' 에서 죽지 않게 UTF-8 고정.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

HERE = Path(__file__).resolve().parent
TARGETS = sorted((HERE / "scenarios").glob("*.json"))
HOSTS = ("mirror.raid.internal", "pkg-telemetry-cdn.net")


def detect_ip() -> str:
    """기본 경로로 나가는 인터페이스의 IP. 패킷을 실제로 보내지는 않는다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))          # 라우팅 테이블 조회용
        return s.getsockname()[0]
    except Exception:
        try: return socket.gethostbyname(socket.gethostname())
        except Exception: return ""
    finally:
        s.close()


def main() -> None:
    ip = sys.argv[1] if len(sys.argv) > 1 else detect_ip()
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", ip or ""):
        sys.exit(f"✗ IP 감지 실패. 직접 지정하세요:  python sync_ip.py 192.168.0.7")
    if ip.startswith("127."):
        print(f"[!] 감지된 IP 가 루프백({ip})입니다. VM 에서 닿지 않으니 직접 지정하세요.")
    print(f"→ 호스트 IP: {ip}")

    # \b 를 쓰면 안 된다 — JSON 안의 '...\\n192.168.0.14 pkg-...' 처럼 IP 앞에
    # 문자가 붙어 있으면 단어 경계가 성립하지 않아 두 번째 호스트가 치환되지 않는다.
    IPPAT   = r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}"
    changed = 0
    for f in TARGETS:
        txt = orig = f.read_text(encoding="utf-8")
        txt = re.sub(IPPAT + r":8000", f"{ip}:8000", txt)                     # URL 참조
        for h in HOSTS:                                                       # /etc/hosts 매핑
            txt = re.sub(IPPAT + r" " + re.escape(h), f"{ip} {h}", txt)
        if txt != orig:
            f.write_text(txt, encoding="utf-8"); changed += 1
            print(f"   갱신 {f.name}")
    if changed:
        print(f"✔ {changed}/{len(TARGETS)} 파일 갱신 → 모두 {ip}")
    else:
        # '0/5 갱신' 은 실패처럼 읽힌다. 바꿀 게 없었다는 뜻임을 분명히 한다.
        print(f"✔ 이미 {ip} 로 맞춰져 있습니다 — 바꿀 것 없음 ({len(TARGETS)}개 파일 확인)")
    print(f"  확인: VM 안에서  curl -s http://{ip}:8000/ | head")


if __name__ == "__main__":
    main()
