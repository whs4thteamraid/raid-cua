#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEM-PERSIST — 6명 결과 취합. results/trials/index_*.csv 를 모아 최종 격자를 낸다.

    python tally.py          (Windows)
    python3 tally.py         (macOS/Linux)

판정은 각자의 run_chain 이 계산해 둔 값을 그대로 쓴다.
"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception: pass

TRIALS = Path(__file__).resolve().parent / "results" / "trials"
ARMS, TASKS = ("faithful", "controlled", "inject"), ("cued", "benign")
VALID = ("발화", "실행저항")            # 이 둘만 유효. 나머지는 무효 시행.
TARGET = 20

rows, files = [], sorted(TRIALS.glob("index_*.csv"))
if not files:
    sys.exit(f"✗ {TRIALS} 에 index_*.csv 가 없습니다. 팀원 결과를 pull 하세요.")
for f in files:
    with f.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["_file"] = f.name
            rows.append(r)

print(f"취합 파일 {len(files)}개 · 시행 {len(rows)}판\n")

valid = Counter(); fired = Counter(); views0 = Counter(); ops = defaultdict(set)
for r in rows:
    k = (r.get("arm"), r.get("task"))
    ops[k].add(r.get("operator") or "?")
    if r.get("verdict") in VALID:
        valid[k] += 1
        if r.get("verdict") == "발화": fired[k] += 1
        if (r.get("p2_views") or "") == "0": views0[k] += 1

print(f"{'셀':24} {'유효':>7} {'발화':>6} {'발화율':>8} {'조회0':>6}  담당")
print("─" * 78)
for arm in ARMS:
    for task in TASKS:
        k = (arm, task); v, f_ = valid[k], fired[k]
        rate = f"{f_/v*100:5.0f}%" if v else "    —"
        mark = "" if v >= TARGET else f"  ← {TARGET-v} 부족"
        print(f"{arm+' × '+task:24} {v:3}/{TARGET:<3} {f_:6} {rate:>8} {views0[k]:6}  "
              f"{','.join(sorted(ops[k])) or '-'}{mark}")

inval = Counter(r.get("verdict") for r in rows if r.get("verdict") not in VALID)
if inval:
    print("\n무효 시행:", "  ".join(f"{k} {n}" for k, n in inval.most_common()))
    tot = len(rows)
    print(f"무효율 {sum(inval.values())/tot*100:.0f}%  "
          f"→ 유효 {TARGET}판을 채우려면 셀당 약 {TARGET/(1-sum(inval.values())/tot):.0f}판 필요")

need = sum(max(0, TARGET - valid[(a, t)]) for a in ARMS for t in TASKS)
print(f"\n남은 시행 {need}판" if need else "\n✔ 전 셀 목표 달성")
