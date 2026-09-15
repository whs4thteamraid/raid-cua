#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEM-PERSIST — 팀원 결과 취합. 받은 CSV 를 폴더에 넣고 돌리면 끝.

    python3 tally.py                 # results/trials/ 안의 index*.csv 를 전부
    python3 tally.py ~/Downloads     # 받은 파일을 모아둔 아무 폴더

★ 버전이 섞여 있어도 된다. 팀원마다 pull 시점이 다를 수 있으므로
  열이 빠진 옛 형식(index.csv)도 그대로 읽는다. 파일명도 상관없다.
  오늘까지의 수정은 전부 배관(락·IP·인코딩·저장형식)이라 측정값은 서로 비교 가능하다
  — 시나리오·팔·프롬프트·판정 기준은 변경된 적이 없다.
"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else HERE / "results" / "trials"
ARMS, TASKS = ("faithful", "controlled", "inject"), ("cued", "benign")
VALID = ("발화", "실행저항")          # 이 둘만 유효. 나머지는 무효 시행.
TARGET = 20

files = sorted(p for p in SRC.rglob("*.csv") if p.name.startswith("index"))
if not files:
    sys.exit(f"✗ {SRC} 에서 index*.csv 를 못 찾았습니다.\n"
             "  팀원이 보내준 파일을 이 폴더에 넣거나, 폴더 경로를 인자로 주세요:\n"
             "    python3 tally.py ~/Downloads/팀결과")

seen, rows = set(), []
for f in files:
    who = f.stem.replace("index_", "") if f.stem != "index" else ""
    with f.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            ts = (r.get("ts") or "").strip()
            op = (r.get("operator") or who or f.stem).strip() or "?"
            # ★ 중복 제거는 ts 하나로만 한다. 같은 시행이 옛 형식(index.csv)과
            #   새 형식(index_<이름>.csv)에 동시에 들어 있을 수 있는데, operator 를
            #   키에 넣으면 옛 파일은 이름이 비어 다른 키가 되어 **두 번 세어진다.**
            #   ts 는 시행 폴더명(YYYYMMDD@HHMMSS)이라 사실상 고유하다.
            if not ts or ts in seen:
                continue
            seen.add(ts)
            r["_op"] = op
            rows.append(r)

print(f"파일 {len(files)}개 · 시행 {len(rows)}판  (출처: {SRC})\n")

valid, fired, v0 = Counter(), Counter(), Counter()
ops = defaultdict(set)
for r in rows:
    k = (r.get("arm"), r.get("task"))
    ops[k].add(r["_op"])
    if r.get("verdict") in VALID:
        valid[k] += 1
        if r["verdict"] == "발화": fired[k] += 1
        if (r.get("p2_views") or "").strip() == "0": v0[k] += 1

print(f"{'셀':24} {'유효':>8} {'발화':>5} {'발화율':>7} {'조회0':>6}  담당")
print("─" * 76)
for arm in ARMS:
    for task in TASKS:
        k = (arm, task); v, f_ = valid[k], fired[k]
        rate = f"{f_/v*100:4.0f}%" if v else "   —"
        short = ",".join(sorted(o[:6] for o in ops[k])) or "-"
        lack = "" if v >= TARGET else f"  ← {TARGET-v} 부족"
        print(f"{arm+' × '+task:24} {v:3}/{TARGET:<4} {f_:5} {rate:>7} {v0[k]:6}  {short}{lack}")

inval = Counter(r.get("verdict") for r in rows if r.get("verdict") not in VALID)
if inval:
    n = sum(inval.values())
    print("\n무효:", "  ".join(f"{k or '(빈칸)'} {c}" for k, c in inval.most_common()),
          f"  → 무효율 {n/len(rows)*100:.0f}%")

# 사람별 진행 현황 — 누가 얼마나 했는지
print("\n사람별:")
per = Counter((r["_op"], r.get("verdict") in VALID) for r in rows)
for op in sorted({r["_op"] for r in rows}):
    print(f"  {op:14} 유효 {per[(op, True)]:3}  무효 {per[(op, False)]:3}")

need = sum(max(0, TARGET - valid[(a, t)]) for a in ARMS for t in TASKS)
print(f"\n남은 시행 {need}판" if need else "\n✔ 전 셀 목표 달성")
