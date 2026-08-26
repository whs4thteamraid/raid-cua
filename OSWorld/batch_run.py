#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
배치 러너 — 한 시나리오를 N번 반복 실행하고 공격 성공률을 집계한다.
(OSWorld VM은 한 번에 하나만 뜨므로 순차 실행)

사용 (OSWorld-audit 루트에서):
    python3 batch_run.py \
        --scenario security_scenarios/ipi_005_delete_important_folder/scenario.json \
        -n 10 --pause 0.5 --initial-wait 1.5

- `--allow-external-screen-share --execute-actions` 는 자동으로 붙는다.
- run_opencua.py 로 넘길 다른 옵션(--pause, --initial-wait, --max-steps 등)은 그대로 전달된다.
- 결과 요약은 batch_results/ 에 JSON 으로 저장. 각 실행의 판단 로그는
  security_results/<id>/<dir>/trajectory.jsonl 에서 볼 수 있다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_opencua.py"
RESULTS = HERE / "security_results"


def scenario_id(scenario_path: str) -> str:
    return json.loads(Path(scenario_path).read_text(encoding="utf-8"))["id"]


def existing_runs(sid: str) -> set[str]:
    base = RESULTS / sid
    return {p.name for p in base.glob("*") if p.is_dir()} if base.exists() else set()


def read_summary(sid: str, dirname: str):
    s = RESULTS / sid / dirname / "summary.json"
    if s.is_file():
        try:
            return json.loads(s.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="시나리오 N회 반복 + 성공률 집계")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("-n", "--runs", type=int, default=10)
    args, passthrough = ap.parse_known_args()

    sid = scenario_id(args.scenario)
    forward = list(passthrough)
    for flag in ("--allow-external-screen-share", "--execute-actions"):
        if flag not in forward:
            forward.append(flag)

    records = []
    succ = blocked = err = 0
    print(f"=== batch: {sid} × {args.runs} ===\n")

    for i in range(1, args.runs + 1):
        before = existing_runs(sid)
        cmd = [sys.executable, str(RUNNER), "--scenario", args.scenario] + forward
        print(f"[{i}/{args.runs}] running ...")
        proc = subprocess.run(cmd)
        new = sorted(existing_runs(sid) - before)
        summary = read_summary(sid, new[-1]) if new else None

        if summary is None:
            err += 1
            score = None
            print(f"[{i}/{args.runs}] ERROR (summary 없음, exit={proc.returncode})")
        else:
            score = summary.get("attack_score")
            term = summary.get("termination")
            if score == 1:
                succ += 1
            elif score == 0:
                blocked += 1
            else:
                err += 1
            print(f"[{i}/{args.runs}] score={score} term={term}  (누적 취약 {succ}/{i})")

        records.append({
            "run": i,
            "dir": new[-1] if new else None,
            "score": score,
            "termination": (summary or {}).get("termination"),
        })

    total = args.runs
    rate = (succ / total * 100) if total else 0.0
    print("\n" + "=" * 50)
    print(f" {sid}  —  {total}회")
    print(f"  ATTACK_SUCCEEDED (취약) : {succ}  ({rate:.0f}%)")
    print(f"  ATTACK_BLOCKED   (방어) : {blocked}")
    print(f"  errors                  : {err}")
    print("=" * 50)

    out_dir = HERE / "batch_results"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"{sid}_{total}runs_{stamp}.json"
    out.write_text(json.dumps({
        "scenario_id": sid,
        "runs": total,
        "attack_succeeded": succ,
        "attack_blocked": blocked,
        "errors": err,
        "success_rate": rate,
        "records": records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {out}")
    print(f"각 실행 판단 로그: security_results/{sid}/<dir>/trajectory.jsonl")


if __name__ == "__main__":
    main()
