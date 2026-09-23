#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""세 판의 조건 지문을 나란히 놓고 '같아야 할 축'이 같은지 판정한다.

    uv run python redteam/compare_conditions.py <시행폴더> <시행폴더> [<시행폴더>]

★ 이 파일의 MUST_MATCH / STRUCTURAL_RESIDUE 두 리스트가 "우리가 무엇을 맞췄고 무엇을
  못 맞췄는지"의 **단일 진실 공급원**이다. 문서에 적힌 주장과 코드가 갈라질 수 없게
  하려고 여기에 둔다. 목록 어디에도 없는 축이 나타나면 경고로 걸리므로, 새 조건을
  추가하면 반드시 둘 중 하나에 넣어야 한다 — 목록이 닫혀 있어야 "이것 말고는 같다"가
  성립하기 때문이다.

종료 코드: 0 = 같은 출발선, 1 = 불일치 있음, 2 = 조건 지문 없음(1단계 미적용).
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

# ── 세 모델이 **같아야** 하는 축 ────────────────────────────────────────────
MUST_MATCH = [
    "history_steps",
    "max_tokens",
    "temperature",
    "image_sent_wh",
    "thinking",
    "max_steps",
    # ★ 행동 예산은 "호출/스텝이 같은가" 가 아니라 **"천장이 구속했는가"** 로 본다.
    #   (실측) haiku 는 phase1 중앙값 38/40 으로 천장에 닿고, Luna 는 10스텝에 끝난다.
    #   아무도 안 닿으면 스텝당 호출 수가 달라도 완수 여부에 영향이 없다. 반대로 한 모델만
    #   닿으면 "못 했다" 와 "스텝이 모자랐다" 를 가를 수 없다 — 그게 진짜 교란이다.
    #   ※ 이 축은 '셋이 같은가' 가 아니라 '셋 다 False 인가' 로 판정한다(main 참조).
    "measured.hit_cap",
]

# ── 구조적으로 **못 맞추는** 축 ─────────────────────────────────────────────
# 다르다고 표시만 하고 실패로 세지 않는다.
# (`공통출발선_3모델_조건정렬_감사.md` §8 의 잔차 목록과 1:1 대응. 늘릴 때는 문서도 같이.)
STRUCTURAL_RESIDUE = [
    "history_unit",            # Luna 는 (스샷+액션+생각) 묶음 수, 나머지는 스크린샷 수
    # reasoning_elicitation — none / forced_reason_line / native
    #   ★ 이 셋은 "행동 전에 이유를 말하는가" 에서는 **이미 같다.** 다른 것은 경로뿐이다.
    #       Haiku : 자연 발화
    #       Luna  : '## Reason:' 한 줄 강제 — stock 프롬프트가 "NEVER EVER RETURN ME
    #               ANYTHING ELSE" 로 산문을 금지해서, 그대로 두면 Luna 만 벙어리가 된다.
    #               즉 이 패치는 차이를 만든 게 아니라 **Haiku 수준으로 끌어올린 보정**이다.
    #       Kimi  : 벤더 NON_THINKING 프롬프트의 '## Thought:' 섹션 (뗄 수 없음)
    #   ⚠️ 여기 'forced_reason_line' 이 보인다고 Luna 패치를 떼지 말 것. 떼면 축이
    #      맞춰지는 게 아니라 Luna 의 사고가 터미널·궤적에서 통째로 사라져 **더 어긋난다.**
    "reasoning_elicitation",
    "tool_channel",            # native_tool_result / user_turn / instruction_prefix
    "system_prompt_sha256",    # 벤더별 프롬프트 계보 (Haiku 우리 것 / Luna stock / Kimi 벤더)
    "system_prompt_len",
    "coordinate_type",         # Kimi 만 가짐 (상대좌표)
    # ★ memory_arm 은 '맞출 수 있는 축'이 아니다 (결정됨).
    #   faithful 은 Anthropic 서버의 auto-view 프로토콜이라 haiku 에만 존재하고,
    #   Luna·Kimi 에 대응물을 두지 않기로 했다. 즉 phase1 에서 세 모델이 같은 팔
    #   문자열이 되는 경우가 구조적으로 없다. MUST_MATCH 에 두면 영영 지워지지 않는
    #   ✗ 가 하나 붙박이로 남아 "남은 ✗ = 할 일" 이라는 신호가 흐려진다.
    #   ⚠️ 단, phase2 는 세 모델이 같은 팔(ARM 인자)을 쓰므로 여기서 걸러지지 않는다.
    #      phase2 팔이 어긋나는 사고는 이 비교기가 못 잡는다 — summary 의
    #      conditions_phase2.memory_arm 을 따로 볼 것.
    "memory_arm",
    # ★ top_p 도 맞출 수 없다 — gpt-5.6 이 top_p 를 거부해서 Luna 는 payload 에서
    #   제거된다(= 영영 None). Claude·Kimi 는 1.0(절단 없음)으로 맞춰 **동작은** 같게
    #   해뒀지만, 기록이 같아질 수는 없다.
    "top_p",
]

# 비교하지 않고 눈으로만 보는 축 (측정 맥락)
INFO = ["one_call_per_step", "reasoning_effort", "kimi_thinking_flag",
        "native_reasoning_chars", "tool_doc_sha256", "tool_doc_len",
        # 호출/스텝은 기록하되 **일치를 요구하지 않는다** — ONE_CALL 이 꺼져 있으면
        # 모델마다 다른 게 정상이고, 중요한 것은 위의 hit_cap 이다.
        "measured.calls_per_step", "measured.gui_calls_per_step", "measured.steps_cap",
        "measured.steps", "measured.gui_steps", "measured.gui_calls"]

# 실측치는 완전 일치를 요구하지 않는다 — 판마다 흔들린다.
TOL = {"measured.gui_calls_per_step": 0.15, "measured.calls_per_step": 0.15}


def known_axes() -> set:
    """비교기가 아는 축 전부.

    ★ 한 곳에서만 정의한다. 예전에는 main() 과 테스트가 각자 이 집합을 조립했고,
      INFO 를 추가했을 때 테스트 쪽만 낡아서 멀쩡한 축을 '목록에 없다' 고 잡았다.
      목록을 닫아두는 장치가 두 벌이면, 그 둘이 어긋나는 순간 장치가 거짓말을 한다.
    """
    return set(MUST_MATCH) | set(STRUCTURAL_RESIDUE) | set(INFO) | {"measured", "error"}

COL = 15


def dwidth(s: str) -> int:
    """터미널 표시 폭. 한글은 두 칸을 먹으므로 len() 으로 맞추면 표가 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def dig(d, dotted):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def load(p):
    f = Path(p) / "summary.json"
    if not f.exists():
        sys.exit(f"✗ {f} 없음")
    s = json.loads(f.read_text(encoding="utf-8"))
    name = s.get("model_key") or s.get("model") or Path(p).name
    return name, (s.get("conditions") or {})


def fmt(v):
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) for x in v):
        return f"{v[0]}x{v[1]}"
    if v is None:
        return "None"
    return str(v)


def _norm(v):
    """비교용 정규화.

    ★ None 을 걸러내지 않는다 — 여기서 None 은 '값 없음'이 아니라 **'안 보냄'** 이라는
      의미 있는 조건이다. 걸러내면 top_p 가 (None, None, 0.95) 일 때 비교 대상이 하나만
      남아 '같다'로 통과해버린다. 실제로 Kimi 만 top_p 가 걸리는데도 ✓ 가 나왔다.
    ★ bool 을 int 보다 먼저 거른다 — isinstance(True, int) 가 True 라서, 안 그러면
      thinking=False 와 top_p=0 이 같은 값으로 뭉개진다.
    ★ 1 과 1.0 은 같게 본다 — 벤더마다 int/float 로 적어둔 차이일 뿐이다.
    """
    if v is None:
        return ("none",)
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float)):
        return ("num", float(v))
    if isinstance(v, list):
        return ("list", tuple(_norm(x) for x in v))
    return ("other", json.dumps(v, sort_keys=True, ensure_ascii=False))


def same(vals, axis):
    if len(vals) < 2:
        return True
    tol = TOL.get(axis)
    if tol is not None:
        nums = [v for v in vals
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(nums) == len(vals):
            return max(nums) - min(nums) <= tol
        # 숫자가 아닌 것이 섞였으면(기록 실패 등) 일반 비교로 떨어진다
    first = _norm(vals[0])
    return all(_norm(v) == first for v in vals)


def main(paths) -> int:
    loaded = [load(p) for p in paths]
    names = [n for n, _ in loaded]
    conds = [c for _, c in loaded]
    if not any(conds):
        print("✗ conditions 블록이 없다 — 1단계(조건 지문)를 적용하고 판을 다시 돌릴 것.")
        return 2

    w = max(26, max(dwidth(a) for a in MUST_MATCH + STRUCTURAL_RESIDUE + INFO) + 2)
    head = pad("축", w) + "".join(pad(n, COL) for n in names)
    print(head)
    print("─" * dwidth(head))

    # ★ GUI 를 한 번도 안 쓴 판에서는 calls_per_step 이 행동 예산을 재지 못한다.
    #   (실측) 스모크 phase1 은 bash/memory 만 쓰므로 세 모델 다 1.0 이 나오고, 그대로
    #   ✓ 를 찍으면 "행동 예산 정렬됨" 으로 오독된다. 그럴 땐 판정을 보류한다.
    gui_seen = any((dig(c, "measured.gui_calls") or 0) > 0 for c in conds)

    fails = []
    for axis in MUST_MATCH:
        vals = [dig(c, axis) for c in conds]
        if axis == "measured.hit_cap":
            vals = [bool(v) for v in vals]
            ok = not any(vals)          # 같은지가 아니라 아무도 안 닿았는지
            if not ok:
                fails.append(axis)
            note = "" if ok else "  ← 천장에 닿은 모델이 있다. max_steps 를 올릴 것"
            print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals)
                  + ("✓" if ok else "✗") + note)
            continue
        if axis == "measured.gui_calls_per_step" and not gui_seen:
            print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals)
                  + "–  GUI 미사용 — 이 판으로는 행동 예산을 못 잰다")
            continue
        ok = same(vals, axis)
        if not ok:
            fails.append(axis)
        print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals)
              + ("✓" if ok else "✗"))

    print("─" * dwidth(head) + "  참고 (비교 안 함)")
    for axis in INFO:
        vals = [dig(c, axis) for c in conds]
        print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals) + "·")

    print("─" * dwidth(head) + "  구조적 잔차 (달라도 됨)")
    for axis in STRUCTURAL_RESIDUE:
        vals = [dig(c, axis) for c in conds]
        print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals) + "~")

    # ★ 목록에 없는 축이 나타나면 알린다 — 목록을 닫아두기 위한 장치.
    known = known_axes()
    unknown = sorted({k for c in conds for k in c} - known)
    if unknown:
        print(f"\n⚠ 목록에 없는 축: {', '.join(unknown)}")
        print("  MUST_MATCH 인지 STRUCTURAL_RESIDUE 인지 정해서 이 파일에 넣을 것.")

    # ★ 플래그와 실측이 어긋나면 잡는다 — "껐다고 적혀 있는데 실제로는 추론했다" 를
    #   놓치면 거짓 ✓ 가 만들어진다. 실제로 Kimi 가 정확히 그 상태였다.
    for name, c in zip(names, conds):
        rc = c.get("native_reasoning_chars")
        if c.get("thinking") is False and isinstance(rc, int) and rc > 0:
            print(f"\n⚠ {name}: thinking=False 인데 네이티브 추론이 {rc}자 관측됐다 "
                  f"— 실제로는 안 꺼진 것이다.")

    errs = [c["error"] for c in conds if c.get("error")]
    for e in errs:
        print(f"\n⚠ 조건 기록 실패: {e}")

    print()
    if fails:
        print(f"✗ {len(fails)}개 불일치 — 아직 같은 출발선이 아니다: {', '.join(fails)}")
        return 1
    print("✓ 같은 출발선 — MUST_MATCH 전부 일치 (위 잔차는 구조적으로 못 맞추는 축)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("사용법: compare_conditions.py <시행폴더> <시행폴더> [<시행폴더>]")
    sys.exit(main(sys.argv[1:]))
