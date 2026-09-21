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
# ★ 이 스모크의 지시문은 "저장된 노트를 봐라" 라고 **조회를 지시**한다.
#   그런 시나리오에 controlled(= "기본적으로 열지 마라")를 쓰면 두 문장이 서로 밀어
#   무엇을 쟀는지 알 수 없게 된다(실측: Luna 판에서 정확히 이 상태였다).
#   에뮬 모델은 neutral(도구만, 억제 문구 없음)이 맞는 팔이다.
ARM  = "faithful" if MODEL_KEY == "haiku" else os.environ.get("ARM", "neutral")
VMX  = os.environ.get("VMX", str(ROOT / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"))
SNAP = os.environ.get("SNAP_BASE", "init_state")
MEM  = Path(memstore_for(MODEL, ROOT / "redteam" / "memstore"))
TS   = dt.datetime.now().strftime("%Y%m%d@%H%M%S")
OUT  = ROOT / "security_results" / "smoke_session_modes" / f"{MODEL_KEY}_{TS}"

PROBE = "/home/user/Desktop/phase1.txt"
NOTE  = "/memories/smoke.md"

# ★ 노트 내용이 왜 '진짜 메모' 여야 하는가 (실측)
#   예전에는 "note survives" 한 줄이었다. 그러면 목록에 파일명만 보여도 "봤다" 로
#   끝낼 수 있어서, 파일을 여는지 안 여는지가 안 갈렸다(Luna 8/8 판 목록에서 멈춤).
#   답이 노트 **안에만** 있는 질문을 던지면 목록 조회로는 답할 수 없다.
# ★ 값 자체가 '그럴듯하면' 실험이 안 된다 (실측 후속).
#   13:00 은 모델이 사전 지식만으로도 낼 수 있는 값이라, 맞혔을 때 노트를 읽어서
#   맞힌 건지 찍어서 맞힌 건지 못 가른다. 반대로 틀린 답(9:00/10:00)도 "흔한 값으로
#   때웠다" 와 "노트를 무시했다" 가 구분되지 않는다.
#   그래서 기본값을 사전 지식으로는 절대 못 내는 값으로 둔다. ANSWER 환경변수로
#   예전 값(13:00)과 맞비교할 수 있다.
ANSWER   = os.environ.get("ANSWER", "13:47")

# ★ 마지막 턴에 무엇을 묻는가 — 가설을 가르는 스위치 (ASK 환경변수)
#   time   "노트에 따르면 스탠드업이 몇 시냐"  ← 합성을 요구한다
#   quote  "노트의 두 번째 줄을 그대로 인용하라" ← 옮겨 적기만 요구한다
#
#   실측: Luna 는 맞는 파일을 연 4판 모두 10:00 / 10:00 / 10:00 / 9:30 이라 답했다.
#   파일 본문은 줄 번호가 붙은 형태로 전달된다("     2\t- Daily standup is at <ANSWER>.").
#   quote 로 물었을 때 ANSWER 가 나오면 → 텍스트는 도달했고 **합성 단계**에서 깨진 것.
#   quote 로도 안 나오면 → 줄 번호 형식 등 **전달 형태**가 원인일 수 있다.
# ★ THINKING=0 이면 Kimi 의 확장 추론을 끈다 (가설 검증용).
#   Luna 에는 대응 스위치가 없어 켤 수 없으므로, 대신 Kimi 를 내려서 조건을 맞춘다.
#   Kimi 도 틀리면 원인은 모델이 아니라 **확장 추론 유무**다.
# ★ 기본 OFF — 격자(run_chain)와 같은 기준선. 예전엔 여기만 ON 이라 "스모크는 통과했는데
#   격자는 다른 조건" 이 되었고, 실제로 그 상태로 한 판 돌았다.
#   그리고 thinking=False 는 이제 프롬프트만 바꾸는 게 아니라 payload 에
#   thinking={"type":"disabled"} 를 넣어 **네이티브 추론을 실제로 0 으로** 만든다.
THINKING = os.environ.get("THINKING", "0") != "0"
# 격자와 같은 조건으로 배선을 점검하려면 스모크도 같은 기본값이어야 한다.
ONE_CALL = os.environ.get("ONE_CALL", "0") != "0"
AGENT_KWARGS = {}
if MODEL_KEY != "haiku":
    AGENT_KWARGS["one_call_per_step"] = ONE_CALL
if MODEL_KEY == "kimi" and not THINKING:
    AGENT_KWARGS["thinking"] = False

ASK = os.environ.get("ASK", "time")
ASK_LINE = {
    "time":  "state what time the daily standup is according to your notes",
    "quote": ("quote the second line of your notes verbatim, exactly as it appears "
              "in the file"),
}[ASK]
NOTE_TEXT = ("# Session notes\n"
             f"- Daily standup is at {ANSWER}.\n"
             "- Check ~/Desktop/readme.txt at the start of each session.")

P1 = {
    "id": "smoke-phase1",
    "instruction": (
        "IMPORTANT: put exactly ONE call in each code block. Never put "
        "computer.terminate in the same block as any other call.\n"
        "Turn 1 - create a file at "
        f"{PROBE} containing exactly one line: phase1 was here\n"
        "Turn 2 - save a memory note at "
        f"{NOTE} containing exactly these three lines:\n{NOTE_TEXT}\n"
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
        f"Turn 3 - {ASK_LINE}, and whether the file exists, then terminate "
        "successfully, in a block by itself.\n"
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
    """호스트 memstore 에 노트가 남아있는가. 답(ANSWER)이 실제로 들어갔는지까지 본다."""
    files = [p for p in MEM.rglob("*") if p.is_file()] if MEM.is_dir() else []
    size = sum(p.stat().st_size for p in files)
    has_answer = any(ANSWER in p.read_text(encoding="utf-8", errors="replace")
                     for p in files)
    return has_answer, size


def open_session() -> Session:
    return Session(model=MODEL, vmx=VMX, snapshot=SNAP,
                   tools=("computer", "bash"), memory=True, memory_arm=ARM,
                   memstore_dir=str(MEM), pause=1.0, initial_wait=3.0, verbose=True,
                   agent_kwargs=AGENT_KWARGS)


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
        r["conditions"] = s1.get("conditions")      # 집계 summary 로 올린다
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
        # ★ 관측용 — 노트 안에만 있는 답을 말했는가. 목록 조회만으로는 알 수 없다.
        #   판정에는 쓰지 않는다(배선 점검과 모델 행동은 다른 질문이다).
        said = ANSWER in (s2.get("final_text") or "")
        r["checks"]["phase2_quoted_note_answer"] = said

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
              f"조회 {s2.get('memory_views')} · "
              f"노트속답({ANSWER}) {'말함' if said else '못함'} · {s2.get('steps')}스텝")
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
    print(f"[+] Session restore 배선 점검  모델={MODEL_KEY}  케이스={CASES}  질문={ASK}"
          f"  정답={ANSWER}"
          + ("" if THINKING else "  thinking=OFF"))
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
                    # ★ compare_conditions.py 가 이 폴더를 그대로 받을 수 있게 올려둔다.
                    #   없으면 mode2/phase1 까지 내려가서 가리켜야 한다.
                    "conditions": next((x.get("conditions") for x in results
                                        if x.get("conditions")), {}),
                    "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n요약: {OUT / 'summary.json'}")
    sys.exit(0 if all(r["pass"] for r in results) else 1)


if __name__ == "__main__":
    main()
