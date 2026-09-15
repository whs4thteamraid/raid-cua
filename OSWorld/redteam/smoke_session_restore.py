#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session 배선 회귀 테스트 — `restore` 인자가 실제로 동작하는가만 본다.

무엇을 재는가
    실행기가 시작 상태를 제대로 만들어 주는지. 공격도 판정도 시나리오도 없다.

        restore="init_state"   되돌리고 시작  → VM 이 한 번 더 꺼졌다 켜져야 한다
        restore=None           지금 VM 그대로 → 앞 판이 만든 것이 살아있어야 한다

어떻게 재는가
    1판이 두 곳에 표식을 남긴다.
        · VM 안:   ~/Desktop/phase1.txt        ← 되돌리면 사라진다
        · 호스트:  memstore 의 노트             ← VM 을 되돌려도 살아남는다
    2판을 돌린 뒤 둘의 생사를 **호스트가 직접** 확인한다(모델 답변을 믿지 않는다).
    실측 근거: 모델이 읽지도 않은 노트 내용을 지어낸 판이 있었다.

★ 지시문이 "한 턴에 하나씩" 을 못박는 이유 (실측)
    KimiAgent 원본 파서(mm_agents/kimi/kimi_agent.py)는 코드 블록 안에
    'computer.terminate' 가 들어 있으면 **그 블록 전체를 버리고** ["DONE"] 하나만
    돌려준다. 그래서 한 블록에 "파일 만들고 · 노트 쓰고 · 종료" 를 함께 쓰면
    앞의 두 행동이 조용히 사라진다(stock OSWorld 에서도 동일). 벤더 코드는
    건드리지 않고, 지시문으로 블록을 쪼개 피한다.

사용법
    uv run python redteam/smoke_session_restore.py [모델] [케이스]
        모델:   haiku | luna | kimi        (기본 kimi)
        케이스: 1 | 2 | 3 | all            (기본 all)
          1 = 1판만            2 = restore=None 으로 2판째
          3 = restore=스냅샷 으로 2판째

    VMX=... 로 VM 경로를 바꿀 수 있다. 어느 폴더에서 실행해도 된다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

# 콘솔 인코딩 고정 — 출력을 파일로 돌리면 Windows 가 cp949 로 죽는다.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if not (ROOT / "desktop_env").is_dir():
    sys.exit(f"✗ OSWorld 루트를 못 찾음: {ROOT}")
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)

MODEL = (sys.argv[1] if len(sys.argv) > 1 else "kimi").strip()
CASES = (sys.argv[2] if len(sys.argv) > 2 else "all").strip()
if CASES not in ("1", "2", "3", "all"):
    sys.exit("케이스는 1 | 2 | 3 | all 중 하나입니다.")

from dotenv import load_dotenv                                      # noqa: E402
load_dotenv(ROOT / ".env")
from mm_agents.adapters.agents import memstore_for, resolve_model_key  # noqa: E402
from redteam.run_cua import Session                            # noqa: E402

MODEL_KEY = resolve_model_key(MODEL)
ARM  = "faithful" if MODEL_KEY == "haiku" else "controlled"
VMX  = os.environ.get("VMX", str(ROOT / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"))
SNAP = os.environ.get("SNAP_BASE", "init_state")
MEM  = Path(memstore_for(MODEL, ROOT / "redteam" / "memstore"))
TS   = dt.datetime.now().strftime("%Y%m%d@%H%M%S")
OUT  = ROOT / "security_results" / "smoke_session_modes" / f"{MODEL_KEY}_{TS}"

PROBE = "/home/user/Desktop/phase1.txt"
NOTE  = "/memories/smoke.md"

P1 = {
    "id": "smoke-phase1",
    "instruction": (
        "IMPORTANT: put exactly ONE call in each code block. Never put "
        "computer.terminate in the same block as any other call.\n"
        "Turn 1 - create a file at "
        f"{PROBE} containing exactly one line: phase1 was here\n"
        "Turn 2 - save a memory note at "
        f"{NOTE} containing exactly one line: note survives\n"
        "Turn 3 - terminate successfully, in a block by itself.\n"
        "Do nothing else."
    ),
    "config": [],
    "evaluator": {"func": "infeasible"},
}
P2 = {
    "id": "smoke-phase2",
    "instruction": (
        "IMPORTANT: put exactly ONE call in each code block. Never put "
        "computer.terminate in the same block as any other call.\n"
        "Turn 1 - look at your saved memory notes.\n"
        "Turn 2 - check whether the file "
        f"{PROBE} exists.\n"
        "Turn 3 - state in one sentence what the notes say and whether the file "
        "exists, then terminate successfully, in a block by itself.\n"
        "Do not create or change any file."
    ),
    "config": [],
    "evaluator": {"func": "infeasible"},
}


def banner(m): print("\n" + "─" * 62 + f"\n{m}\n" + "─" * 62, flush=True)


def probe_file(sess) -> bool:
    """VM 안의 표식 파일 존재 여부. 모델 답변이 아니라 호스트가 직접 본다."""
    out = sess.shell(f"test -f {PROBE} && echo __YES__ || echo __NO__")
    return "__YES__" in out


def probe_note() -> tuple[bool, int]:
    """호스트 memstore 에 노트가 남아있는가."""
    files = [p for p in MEM.rglob("*") if p.is_file()] if MEM.is_dir() else []
    return bool(files), sum(p.stat().st_size for p in files)


def open_session() -> Session:
    return Session(model=MODEL, vmx=VMX, snapshot=SNAP,
                   tools=("computer", "bash"), memory=True, memory_arm=ARM,
                   memstore_dir=str(MEM), pause=1.0, initial_wait=3.0, verbose=True)


def run_mode(mode: int) -> dict:
    """한 케이스를 통째로 돌리고 판정 dict 를 돌려준다."""
    rd = OUT / f"mode{mode}"
    banner(f"케이스 {mode} — {MODEL_KEY}")

    # 매 케이스 시작 시 memstore 를 비운다(케이스 간 오염 방지).
    if MEM.exists():
        shutil.rmtree(MEM, ignore_errors=True)
    MEM.mkdir(parents=True, exist_ok=True)

    r = {"mode": mode, "model_key": MODEL_KEY, "pass": False, "checks": {}, "steps": {}}
    sess = None
    try:
        sess = open_session()

        # ── 1판째 (세 케이스 공통) ────────────────────────────────
        print("[+] Phase1 — 표식 파일 + 메모리 노트 생성")
        s1 = sess.run(P1, result_dir=rd / "phase1", restore=SNAP,
                      max_steps=12, evaluate=False)
        r["steps"]["phase1"] = s1.get("steps")
        f_after1 = probe_file(sess)
        n_after1, n_bytes = probe_note()
        r["checks"]["phase1_file"] = f_after1
        r["checks"]["phase1_note"] = n_after1
        print(f"[=] Phase1 결과 — 파일 {'있음' if f_after1 else '없음'} · "
              f"노트 {'있음' if n_after1 else '없음'}({n_bytes}B) · {s1.get('steps')}스텝")

        if not (f_after1 and n_after1):
            r["note"] = "1판째가 표식을 안 남김 — 판정 불가(모델 문제, 실행기 문제 아님)"
            return r

        if mode == 1:
            # 에피소드 1회로 끝. Phase1 이 남긴 것이 확인되면 그것으로 충분하다.
            r["pass"] = True
            return r

        # ── Phase 2 ───────────────────────────────────────────────
        restore = None if mode == 2 else SNAP
        print(f"[+] Phase2 — restore={restore!r} "
              f"({'같은 VM 이어서' if restore is None else 'VM 완전 초기화'})")
        s2 = sess.run(P2, result_dir=rd / "phase2", restore=restore,
                      max_steps=10, evaluate=False)
        r["steps"]["phase2"] = s2.get("steps")
        r["checks"]["phase2_memory_views"] = s2.get("memory_views")

        f_after2 = probe_file(sess)
        n_after2, n_bytes2 = probe_note()
        r["checks"]["phase2_file"] = f_after2
        r["checks"]["phase2_note"] = n_after2

        # 기대값 — VM 파일은 갈리고, 호스트 노트는 어느 쪽이든 살아있어야 한다.
        want_file = True if mode == 2 else False
        r["checks"]["expected_file"] = want_file
        r["pass"] = (f_after2 == want_file) and n_after2
        print(f"[=] Phase2 결과 — VM 파일 {'있음' if f_after2 else '없음'} "
              f"(기대 {'있음' if want_file else '없음'}) · "
              f"호스트 노트 {'있음' if n_after2 else '없음'}({n_bytes2}B) · "
              f"조회 {s2.get('memory_views')} · {s2.get('steps')}스텝")
        return r
    except KeyboardInterrupt:
        r["note"] = "사용자 중단"
        raise
    except Exception as exc:                                        # noqa: BLE001
        r["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[!] 케이스 {mode} 실패: {r['error']}")
        return r
    finally:
        if sess is not None:
            try: sess.close()
            except Exception: pass
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "verdict.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"[+] Session restore 배선 점검  모델={MODEL_KEY}  케이스={CASES}")
    print(f"[+] 결과 폴더: {OUT}")

    cases = [1, 2, 3] if CASES == "all" else [int(CASES)]
    results = []
    for m in cases:
        results.append(run_mode(m))

    banner("결과")
    label = {1: "1판만", 2: "restore=None", 3: "restore=스냅샷"}
    for r in results:
        mark = "✔ 통과" if r["pass"] else "✗ 실패"
        extra = r.get("error") or r.get("note") or ""
        print(f"  케이스 {r['mode']} ({label[r['mode']]:<16}) {mark}   {extra}")
    (OUT / "summary.json").write_text(
        json.dumps({"model": MODEL, "model_key": MODEL_KEY, "arm": ARM,
                    "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n요약: {OUT / 'summary.json'}")
    sys.exit(0 if all(r["pass"] for r in results) else 1)


if __name__ == "__main__":
    main()
