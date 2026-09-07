#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEM-PERSIST — 자체 점검기. VM 도 API 도 쓰지 않고 10초 안에 끝난다.

    python selftest.py          (macOS / Linux / Windows 공통)

무엇을 보는가:
  이 폴더의 코드가 **이 컴퓨터에서** 의도대로 도는지. 이식 과정에서 OS 마다 다르게
  동작하는 지점(경로, 권한, 인코딩, 시각 포맷, 파일 락)을 전부 실제로 태워 본다.
  실험 자체(VM 기동·모델 호출)는 하지 않으므로 비용도 부작용도 없다.

무엇을 못 보는가:
  vmrun 이 실제로 VM 을 띄우는지, 모델이 응답하는지. 그건 첫 시행이 답한다.
"""
from __future__ import annotations

import io
import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = [sys.executable]

_results: list[tuple[str, bool, str]] = []


def check(name):
    """테스트 하나를 등록하는 데코레이터. 예외는 실패로 잡는다."""
    def deco(fn):
        try:
            detail = fn() or ""
            _results.append((name, True, detail))
        except AssertionError as e:
            _results.append((name, False, str(e)))
        except Exception as e:
            _results.append((name, False, f"{type(e).__name__}: {e}"))
        ok = _results[-1][1]
        print(f"  {'✔' if ok else '✗'} {name}" + (f"\n      {_results[-1][2]}" if _results[-1][2] else ""))
        return fn
    return deco


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


# ══════════════════════════════════════════════════════════════════
print(f"MEM-PERSIST 자체 점검  —  {platform.system()} {platform.machine()}  "
      f"Python {sys.version.split()[0]}")
print(f"폴더: {HERE}")
print(f"OSWorld 루트: {ROOT}\n")

print("── 1. 환경 ──")


@check("OSWorld 루트를 올바르게 찾는다")
def _():
    assert (ROOT / "redteam" / "run_claude_3.py").is_file(), \
        f"redteam/run_claude_3.py 없음 — 이 폴더가 security_scenarios/MEM-PERSIST/ 안에 있어야 함"


@check("git 사용 가능 (사내 미러 저장소 생성에 필요)")
def _():
    assert shutil.which("git"), "git 없음 → Windows: Git for Windows 설치"


@check("uv 사용 가능 (실행기 구동에 필요)")
def _():
    assert shutil.which("uv"), "uv 없음 → https://docs.astral.sh/uv/"


@check("vmrun 이 PATH 에 있다 (OSWorld provider 가 요구)")
def _():
    v = shutil.which("vmrun")
    assert v, ("PATH 에 없음. VMRUN_BIN 으로는 대체 안 된다(provider 가 맨 이름으로 부름)\n"
               "      Windows : $env:PATH += ';C:\\Program Files (x86)\\VMware\\VMware Workstation'\n"
               "      macOS   : export PATH=\"$PATH:/Applications/VMware Fusion.app/Contents/Public\"")
    return v


@check(".env 존재 (ANTHROPIC_API_KEY)")
def _():
    assert (ROOT / ".env").is_file(), f"{ROOT / '.env'} 없음"


print("\n── 2. 코드 무결성 ──")


@check("전 스크립트 문법 정상")
def _():
    import ast
    bad = []
    for f in sorted(HERE.glob("*.py")):
        if f.name == "selftest.py":
            continue
        try: ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e: bad.append(f"{f.name}:{e.lineno}")
    assert not bad, "문법 오류: " + ", ".join(bad)
    return f"{len(list(HERE.glob('*.py'))) - 1}개 파일"


@check("잘못된 인자를 거부한다")
def _():
    for script, args in (("run_chain.py", ["bogus", "cued"]),
                         ("run_cell.py", ["X", "y", "z"])):
        r = subprocess.run(PY + [str(HERE / script), *args],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        assert "사용법" in (r.stdout + r.stderr), f"{script} 가 잘못된 인자를 통과시킴"


print("\n── 3. OS 마다 갈리는 지점 ──")


@check("시각 포맷이 이 OS 에서 동작 (%F/%T 는 Windows 에서 죽는다)")
def _():
    import datetime as dt
    s = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", s), f"예상 밖 형식: {s}"
    return s


@check("UTF-8 출력 고정 — 리다이렉트해도 이모지가 안 죽는다")
def _():
    code = ("import sys\n"
            "for s in (sys.stdout, sys.stderr):\n"
            "    try: s.reconfigure(encoding='utf-8', errors='replace')\n"
            "    except Exception: pass\n"
            "print('발화=\u2705 정리=\u2714 실패=\u2717')\n")
    env = dict(os.environ, PYTHONIOENCODING="cp949")     # 한글 Windows 콘솔 흉내
    r = subprocess.run(PY + ["-c", code], capture_output=True, env=env, timeout=60)
    assert r.returncode == 0, "UnicodeEncodeError 로 죽음 — 인코딩 고정이 안 먹음"
    assert "\u2705".encode() in r.stdout, "이모지가 유실됨"


@check("wipe_dir — 읽기전용 파일·디렉토리를 지우고, 권한을 파괴하지 않는다")
def _():
    src = (HERE / "run_chain.py").read_text(encoding="utf-8")
    blk = src[src.index("def unlock_tree(root)"):src.index("\n# (2) 타임스탬프")]
    ns: dict = {}
    exec("import os, shutil, stat\nfrom pathlib import Path\n" + blk, ns)

    t = Path(tempfile.mkdtemp()) / "w"
    (t / "a" / "b").mkdir(parents=True)
    (t / "a" / "b" / "note.md").write_text("x", encoding="utf-8")
    (t / "a" / "obj").write_text("git-like", encoding="utf-8")
    os.chmod(t / "a" / "obj", 0o444)                 # git loose object 흉내
    os.chmod(t / "a" / "b" / "note.md", 0o400)
    os.chmod(t / "a" / "b", 0o500)                   # 읽기전용 디렉토리
    ns["wipe_dir"](t)
    assert t.exists() and not any(t.rglob("*")), "비우지 못함"
    mode = stat.S_IMODE(os.stat(t).st_mode)
    assert mode & stat.S_IRUSR and mode & stat.S_IXUSR, \
        f"권한이 파괴됨(모드 {oct(mode)}) — 읽기·실행이 사라지면 폴더가 접근 불능이 된다"
    shutil.rmtree(t.parent, ignore_errors=True)


@check("삭제 실패를 조용히 넘기지 않는다")
def _():
    src = (HERE / "run_chain.py").read_text(encoding="utf-8")
    blk = src[src.index("def unlock_tree(root)"):src.index("\n# (2) 타임스탬프")]
    ns: dict = {}
    exec("import os, shutil, stat\nfrom pathlib import Path\n" + blk, ns)
    u = Path(tempfile.mkdtemp()) / "u"; u.mkdir()
    (u / "keep.txt").write_text("x", encoding="utf-8")
    orig = ns["shutil"].rmtree
    ns["shutil"].rmtree = lambda *a, **k: None       # 삭제가 조용히 실패하는 상황
    try:
        try:
            ns["wipe_dir"](u)
            raise AssertionError("조용한 실패를 못 잡음 — 이전 시행 노트가 남아 다음 시행을 오염시킨다")
        except RuntimeError:
            pass
    finally:
        ns["shutil"].rmtree = orig
        shutil.rmtree(u.parent, ignore_errors=True)


@check("동시 실행 락 — 두 번째 실행기를 거부한다")
def _():
    src = (HERE / "run_chain.py").read_text(encoding="utf-8")
    blk = src[src.index("_LOCK_FH = None"):src.index("def write_row")]
    tmp = Path(tempfile.mkdtemp())

    def mk():
        import datetime as dt
        ns = {"os": os, "sys": sys, "dt": dt, "HERE": tmp,
              "TS_FMT": "%Y-%m-%d %H:%M:%S", "open": open, "print": lambda *a, **k: None}
        exec(blk, ns); return ns

    a = mk(); a["acquire_lock"]("selftest #1")
    b = mk()
    try:
        b["acquire_lock"]("selftest #2")
        raise AssertionError("두 번째도 통과 — 동시 실행이 막히지 않는다")
    except SystemExit:
        pass
    finally:
        try: a["_LOCK_FH"].close()
        except Exception: pass
        shutil.rmtree(tmp, ignore_errors=True)


@check("경로 길이가 Windows 한계(260) 안에 든다")
def _():
    longest = max(
        len(str(ROOT / "security_results" / "claude_mem-persist-chain-A-benign"
                / "20260908@051910" / "phase2" / "step_035.png")),
        len(str(HERE / "repo" / "raid-mirror.git" / "objects" / "3a"
                / "47b7b5ec487dff2d32386cdf5eb325686de0e7")))
    assert longest < 250, (f"최장 {longest}자 — Windows MAX_PATH 위험. "
                           "레포를 더 짧은 경로(C:\\raid-cua 등)로 옮기세요")
    return f"최장 {longest}자"


print("\n── 4. 시나리오·배선 ──")


@check("시나리오 JSON 5개 파싱 정상")
def _():
    files = sorted((HERE / "scenarios").glob("*.json"))
    assert len(files) == 5, f"5개여야 하는데 {len(files)}개"
    for f in files:
        json.loads(f.read_text(encoding="utf-8"))
    return ", ".join(f.stem for f in files)


@check("시나리오 IP 가 이 컴퓨터의 IP 와 일치")
def _():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]
    except Exception: ip = ""
    finally: s.close()
    assert ip, "IP 감지 실패 — python sync_ip.py <IP> 로 직접 지정하세요"
    txt = (HERE / "scenarios" / "A_cued.json").read_text(encoding="utf-8")
    assert ip in txt, f"시나리오는 다른 IP 를 가리킴 (이 컴퓨터: {ip}) → python sync_ip.py 실행"
    return ip


@check("시나리오에 낡은 IP 가 섞여 있지 않다")
def _():
    ips = set()
    for f in (HERE / "scenarios").glob("*.json"):
        ips |= set(re.findall(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}", f.read_text(encoding="utf-8")))
    assert len(ips) == 1, f"IP 가 여러 개 섞임: {sorted(ips)} — sync_ip.py 사각지대"
    return sorted(ips)[0]


@check("정본 노트 2종 존재")
def _():
    for n in ("NOTE_A.md", "NOTE_B.md"):
        assert (HERE / "notes" / n).is_file(), f"notes/{n} 없음"


print("\n── 5. 사내 미러 서버 (실제 기동 + git clone) ──")

_srv = None
_port = free_port()


@check("serve.py 기동 → bare 저장소 생성")
def _():
    global _srv
    env = dict(os.environ, PORT=str(_port), PYTHONIOENCODING="utf-8")
    _srv = subprocess.Popen(PY + [str(HERE / "serve.py")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{_port}/admin/state", timeout=1).read()
            return f"포트 {_port}"
        except Exception:
            if _srv.poll() is not None:
                raise AssertionError("기동 실패:\n      " + (_srv.stdout.read() or "")[-500:])
            time.sleep(0.5)
    raise AssertionError("30초 안에 안 뜸")


@check("VM 이 하듯 git clone 이 실제로 된다")
def _():
    dst = Path(tempfile.mkdtemp()) / "c"
    r = subprocess.run(["git", "clone", "-q", f"http://127.0.0.1:{_port}/raid-mirror.git", str(dst)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"clone 실패: {(r.stderr or '').strip()[:300]}"
    assert (dst / "setup.sh").is_file(), "setup.sh 가 안 받아짐"
    raw = (dst / "setup.sh").read_bytes()
    assert b"\r\n" not in raw, "setup.sh 가 CRLF — VM 의 bash 가 'bad interpreter: ^M' 로 죽는다"
    files = sorted(p.name for p in dst.iterdir() if p.name != ".git")
    shutil.rmtree(dst.parent, ignore_errors=True)
    return "LF 정상 · " + ", ".join(files)


@check("오염 README 가 서빙된다")
def _():
    body = urllib.request.urlopen(f"http://127.0.0.1:{_port}/raid-mirror/", timeout=5).read().decode("utf-8", "replace")
    assert "setup.sh" in body, "README 에 setup.sh 지시가 없음 — 저장소가 낡았을 수 있음"


@check("경로 탈출 차단")
def _():
    import urllib.error
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{_port}/raid-mirror.git/../serve.py", timeout=5)
        raise AssertionError("탈출이 통과함")
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"403 이어야 하는데 {e.code}"


if _srv is not None:
    _srv.terminate()
    try: _srv.wait(timeout=10)
    except Exception: _srv.kill()

# ══════════════════════════════════════════════════════════════════
ok = sum(1 for _, p, _ in _results if p)
ng = len(_results) - ok
print("\n" + "═" * 64)
print(f"통과 {ok} / 실패 {ng}")
if ng:
    print("\n실패 항목:")
    for name, passed, detail in _results:
        if not passed:
            print(f"  ✗ {name}\n      {detail}")
    print("\n→ 위 항목을 해결한 뒤 실험을 시작하세요.")
else:
    print("→ 이 컴퓨터에서 실험을 시작할 수 있습니다.")
    print("   남은 확인은 첫 시행이 해줍니다(VM 기동 · 모델 응답).")
sys.exit(0 if ng == 0 else 1)
