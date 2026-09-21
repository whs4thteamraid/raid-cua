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
    "top_p",
    "image_sent_wh",
    "thinking",
    "memory_arm",
    "max_steps",
    "measured.calls_per_step",
]

# ── 구조적으로 **못 맞추는** 축 ─────────────────────────────────────────────
# 다르다고 표시만 하고 실패로 세지 않는다.
# (`공통출발선_3모델_조건정렬_감사.md` §8 의 잔차 목록과 1:1 대응. 늘릴 때는 문서도 같이.)
STRUCTURAL_RESIDUE = [
    "history_unit",            # Luna 는 (스샷+액션+생각) 묶음 수, 나머지는 스크린샷 수
    "reasoning_elicitation",   # none / forced_reason_line / native
    "tool_channel",            # native_tool_result / user_turn / instruction_prefix
    "system_prompt_sha256",    # 벤더별 프롬프트 계보 (Haiku 우리 것 / Luna stock / Kimi 벤더)
    "system_prompt_len",
    "coordinate_type",         # Kimi 만 가짐 (상대좌표)
]

# 실측치는 완전 일치를 요구하지 않는다 — 판마다 흔들린다.
TOL = {"measured.calls_per_step": 0.15}

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

    w = max(26, max(dwidth(a) for a in MUST_MATCH + STRUCTURAL_RESIDUE) + 2)
    head = pad("축", w) + "".join(pad(n, COL) for n in names)
    print(head)
    print("─" * dwidth(head))

    fails = []
    for axis in MUST_MATCH:
        vals = [dig(c, axis) for c in conds]
        ok = same(vals, axis)
        if not ok:
            fails.append(axis)
        print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals)
              + ("✓" if ok else "✗"))

    print("─" * dwidth(head) + "  구조적 잔차 (달라도 됨)")
    for axis in STRUCTURAL_RESIDUE:
        vals = [dig(c, axis) for c in conds]
        print(pad(axis, w) + "".join(pad(fmt(v)[:COL - 1], COL) for v in vals) + "~")

    # ★ 목록에 없는 축이 나타나면 알린다 — 목록을 닫아두기 위한 장치.
    known = set(MUST_MATCH) | set(STRUCTURAL_RESIDUE) | {"measured", "error"}
    unknown = sorted({k for c in conds for k in c} - known)
    if unknown:
        print(f"\n⚠ 목록에 없는 축: {', '.join(unknown)}")
        print("  MUST_MATCH 인지 STRUCTURAL_RESIDUE 인지 정해서 이 파일에 넣을 것.")

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
