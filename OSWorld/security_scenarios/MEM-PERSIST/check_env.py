#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEM-PERSIST — 돌리기 전 환경 점검 (OS 무관)."""
from __future__ import annotations
import os, platform, shutil, socket, sys, urllib.request
from pathlib import Path

# 출력을 파일·파이프로 돌렸을 때 Windows(cp949)가 '✔' 에서 죽지 않게 UTF-8 고정.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SERVER = os.environ.get("SERVER", "http://127.0.0.1:8000")
ok = ng = 0

def chk(cond, msg, hint=""):
    global ok, ng
    if cond: print(f"  ✔ {msg}"); ok += 1
    else:    print(f"  ✗ {msg}" + (f"\n      → {hint}" if hint else "")); ng += 1

def detect_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except Exception: return ""
    finally: s.close()

print(f"OS: {platform.system()} {platform.machine()}  |  Python {sys.version.split()[0]}")
print(f"OSWorld 루트: {ROOT}")
chk((ROOT / "redteam" / "run_claude_3.py").is_file(), "표준 실행기 존재")
chk(shutil.which("uv") is not None, "uv 설치됨", "https://docs.astral.sh/uv/")
chk(shutil.which("git") is not None, "git 설치됨 (사내 미러 저장소 생성에 필요)")
# ★ VMRUN_BIN 은 이 폴더의 스크립트만 커버한다. OSWorld 의 vmware provider 는
#   shell=True 로 맨 이름 'vmrun' 을 부르므로 **PATH 등록이 필수**다.
chk(shutil.which("vmrun") is not None, "vmrun 이 PATH 에 있음 (OSWorld provider 가 요구)",
    "Windows 기본 경로: C:\\Program Files (x86)\\VMware\\VMware Workstation\n"
    "        PowerShell(현재 세션만): $env:PATH += ';C:\\Program Files (x86)\\VMware\\VMware Workstation'\n"
    "        macOS: /Applications/VMware Fusion.app/Contents/Public")
chk((ROOT / ".env").is_file(), ".env 존재 (ANTHROPIC_API_KEY)")
chk((HERE / "notes" / "NOTE_A.md").is_file() and (HERE / "notes" / "NOTE_B.md").is_file(),
    "정본 노트 2종 존재")
chk(len(list((HERE / "scenarios").glob("[AB]_*.json"))) == 4, "시나리오 4종 존재")

ip = detect_ip()
if ip:
    txt = (HERE / "scenarios" / "B_cued.json").read_text(encoding="utf-8")
    chk(ip in txt, f"시나리오 IP 가 현재 호스트 IP({ip}) 와 일치",
        f"python sync_ip.py  를 실행하세요")

try:
    urllib.request.urlopen(f"{SERVER}/admin/state", timeout=3).read()
    chk(True, f"serve.py 기동 중 ({SERVER})")
except Exception:
    chk(False, "serve.py 기동", f"다른 터미널에서:  python {HERE / 'serve.py'}")

print(f"\n요약: 통과 {ok} / 실패 {ng}")
print("→ 실행 가능" if ng == 0 else "→ 위 ✗ 항목부터 해결")
sys.exit(0 if ng == 0 else 1)
