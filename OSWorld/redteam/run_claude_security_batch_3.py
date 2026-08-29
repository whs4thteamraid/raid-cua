#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repeat one attack scenario with run_claude_3 and aggregate its results.

The scenario, setup/reset code, artifacts, evaluator, markers, and default
maximum steps are never changed by this helper.  Every child process runs
``redteam.run_claude_3`` with the same requested configuration.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


PROJECT_DIR = next(
    (path for path in Path(__file__).resolve().parents if (path / "desktop_env").is_dir()),
    Path(__file__).resolve().parent,
)
SECURITY_RESULTS = PROJECT_DIR / "security_results"
BATCH_RESULTS = PROJECT_DIR / "batch_results" / "claude_security_run3"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="run_claude_3 기반 Claude CUA 보안 시나리오 반복 실행·집계"
    )
    parser.add_argument("--scenario", required=True)
    parser.add_argument("-n", "--runs", type=int, default=5)
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--tools", default=None)
    parser.add_argument("--type", choices=("gui", "tool"), default="gui")
    parser.add_argument("--path-to-vm", default=None)
    parser.add_argument("--snapshot", default="init_state")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--pause", type=float, default=None)
    parser.add_argument("--initial-wait", type=float, default=None)
    parser.add_argument("--send-width", type=int, default=None)
    parser.add_argument("--between-runs", type=float, default=2.0)

    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memstore-dir", default=None)
    parser.add_argument(
        "--read-mode", choices=("faithful", "controlled", "inject"), default="faithful"
    )
    parser.add_argument("--mcp-config", default=None)

    prompt = parser.add_mutually_exclusive_group()
    prompt.add_argument("--system-prompt", default=None)
    prompt.add_argument("--system-prompt-file", default=None)
    parser.add_argument(
        "--system-prompt-mode", choices=("append", "replace"), default=None
    )
    parser.add_argument(
        "--approval-mode", choices=("off", "interactive"), default="off"
    )

    parser.add_argument("--inject-popup", action="store_true")
    parser.add_argument("--popup-pos", choices=("center", "bottom", "top"), default=None)
    parser.add_argument("--popup-no-ad", action="store_true")
    parser.add_argument("--popup-xy", default=None)

    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.between_runs < 0:
        parser.error("--between-runs cannot be negative")
    if args.max_steps is not None and args.max_steps < 1:
        parser.error("--max-steps must be at least 1")
    if args.approval_mode == "interactive" and args.runs > 1:
        print(
            "[!] interactive 승인 요청은 각 child 실행의 전면 PowerShell에서 반복될 수 있습니다."
        )
    return args


def read_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def existing_run_dirs(result_root: Path) -> set[str]:
    if not result_root.is_dir():
        return set()
    return {path.name for path in result_root.iterdir() if path.is_dir()}


def select_new_run(result_root: Path, before: set[str]) -> Optional[Path]:
    if not result_root.is_dir():
        return None
    candidates = [
        path for path in result_root.iterdir() if path.is_dir() and path.name not in before
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def security_value(summary: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in summary:
        return summary[key]
    nested = summary.get("security_evaluation")
    if isinstance(nested, dict) and key in nested:
        return nested[key]
    return default


def error_text(
    return_code: int,
    summary: Optional[dict[str, Any]],
    run_dir: Optional[Path],
) -> Optional[str]:
    reasons: list[str] = []
    if return_code != 0:
        reasons.append(f"runner exit code {return_code}")
    if run_dir is None:
        reasons.append("result directory not created")
    if summary is None:
        reasons.append("summary.json missing or invalid")
    else:
        if summary.get("error"):
            reasons.append(str(summary["error"]))
        if summary.get("security_evaluation_error"):
            reasons.append(f"security_evaluation: {summary['security_evaluation_error']}")
        nested = summary.get("security_evaluation")
        if isinstance(nested, dict) and (
            nested.get("environment_error") is True
            or nested.get("result") == "ENVIRONMENT_ERROR"
        ):
            reasons.append("security_evaluation reported ENVIRONMENT_ERROR")
    return "; ".join(reasons) if reasons else None


def _add_value(command: list[str], option: str, value: Any) -> None:
    if value is not None:
        command.extend((option, str(value)))


def build_runner_command(args: argparse.Namespace, scenario_path: Path) -> list[str]:
    command = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "redteam.run_claude_3",
        "--scenario",
        str(scenario_path),
        "--snapshot",
        args.snapshot,
        "--model",
        args.model,
        "--approval-mode",
        args.approval_mode,
        "--allow-external-screen-share",
        "--execute-actions",
    ]
    if args.tools:
        command.extend(("--tools", args.tools))
    else:
        command.extend(("--type", args.type))

    _add_value(command, "--path-to-vm", args.path_to_vm)
    _add_value(command, "--max-steps", args.max_steps)
    _add_value(command, "--pause", args.pause)
    _add_value(command, "--initial-wait", args.initial_wait)
    _add_value(command, "--send-width", args.send_width)
    _add_value(command, "--memstore-dir", args.memstore_dir)
    _add_value(command, "--mcp-config", args.mcp_config)
    _add_value(command, "--system-prompt", args.system_prompt)
    _add_value(command, "--system-prompt-file", args.system_prompt_file)
    _add_value(command, "--system-prompt-mode", args.system_prompt_mode)
    _add_value(command, "--popup-pos", args.popup_pos)
    _add_value(command, "--popup-xy", args.popup_xy)

    if args.memory:
        command.extend(("--memory", "--read-mode", args.read_mode))
    if args.inject_popup:
        command.append("--inject-popup")
    if args.popup_no_ad:
        command.append("--popup-no-ad")
    return command


def percentage(count: int, denominator: int) -> Optional[float]:
    return round(count / denominator * 100.0, 2) if denominator else None


def display_bool(value: Optional[bool]) -> str:
    if value is True:
        return "Y"
    if value is False:
        return "N"
    return "-"


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    valid_records = [record for record in records if record["valid"]]
    valid = len(valid_records)
    exposed_records = [
        record for record in valid_records if record["attack_surface_loaded"] is True
    ]
    exposed = len(exposed_records)
    steps = [
        record["steps"]
        for record in valid_records
        if isinstance(record.get("steps"), int)
    ]

    counts = {
        "attack_surface_loaded": sum(
            record["attack_surface_loaded"] is True for record in records
        ),
        "attack_started": sum(record["attack_started"] is True for record in valid_records),
        "attack_partial": sum(record["attack_partial"] is True for record in valid_records),
        "attack_end_to_end": sum(
            record["attack_end_to_end"] is True for record in valid_records
        ),
        "normal_task_success": sum(
            record["normal_task_success"] is True for record in valid_records
        ),
        "safe_completion": sum(record["safe_completion"] is True for record in valid_records),
        "general_failure": sum(
            record["result"] == "GENERAL_FAILURE" for record in valid_records
        ),
        "errors": total - valid,
        "approval_requests": sum(int(record.get("approval_requests") or 0) for record in records),
        "approval_grants": sum(int(record.get("approval_grants") or 0) for record in records),
        "approval_denials": sum(int(record.get("approval_denials") or 0) for record in records),
        "mcp_tool_calls": sum(int(record.get("mcp_tool_call_count") or 0) for record in records),
        "mcp_tool_errors": sum(int(record.get("mcp_tool_error_count") or 0) for record in records),
        "memory_views": sum(int(record.get("memory_views") or 0) for record in records),
        "memory_writes": sum(int(record.get("memory_writes") or 0) for record in records),
    }
    conditional_partial = sum(
        record["attack_partial"] is True for record in exposed_records
    )
    conditional_e2e = sum(
        record["attack_end_to_end"] is True for record in exposed_records
    )
    return {
        "denominators": {
            "total_runs": total,
            "valid_runs": valid,
            "exposed_valid_runs": exposed,
        },
        "counts": counts,
        "steps": {
            "average": round(sum(steps) / len(steps), 2) if steps else None,
            "minimum": min(steps) if steps else None,
            "maximum": max(steps) if steps else None,
        },
        "rates_percent": {
            "attack_surface_exposure_rate": percentage(counts["attack_surface_loaded"], total),
            "attack_action_start_rate": percentage(counts["attack_started"], valid),
            "partial_asr": percentage(counts["attack_partial"], valid),
            "end_to_end_asr": percentage(counts["attack_end_to_end"], valid),
            "normal_task_success_rate": percentage(counts["normal_task_success"], valid),
            "safe_completion_rate": percentage(counts["safe_completion"], valid),
            "general_task_failure_rate": percentage(counts["general_failure"], valid),
            "error_rate": percentage(counts["errors"], total),
            "conditional_partial_asr_given_exposure": percentage(
                conditional_partial, exposed
            ),
            "conditional_end_to_end_asr_given_exposure": percentage(
                conditional_e2e, exposed
            ),
        },
    }


def print_run_table(records: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 118)
    print(
        f"{'Run':>3}  {'Valid':>5}  {'Surface':>7}  {'Start':>5}  "
        f"{'Partial':>7}  {'E2E':>3}  {'Normal':>6}  {'Steps':>5}  "
        f"{'Result':<24}  Directory"
    )
    print("-" * 118)
    for record in records:
        steps = record["steps"] if isinstance(record.get("steps"), int) else "-"
        print(
            f"{record['run']:>3}  {display_bool(record['valid']):>5}  "
            f"{display_bool(record['attack_surface_loaded']):>7}  "
            f"{display_bool(record['attack_started']):>5}  "
            f"{display_bool(record['attack_partial']):>7}  "
            f"{display_bool(record['attack_end_to_end']):>3}  "
            f"{display_bool(record['normal_task_success']):>6}  {str(steps):>5}  "
            f"{record['result']:<24}  {record['directory'] or '-'}"
        )
    print("=" * 118)


def print_metrics(metrics: dict[str, Any]) -> None:
    denominators = metrics["denominators"]
    counts = metrics["counts"]
    rates = metrics["rates_percent"]
    steps = metrics["steps"]
    print("\n집계 결과")
    print(
        f"  전체={denominators['total_runs']}  유효={denominators['valid_runs']}  "
        f"노출된 유효 실행={denominators['exposed_valid_runs']}"
    )
    for label, rate_key, count_key in (
        ("공격 표면 노출률", "attack_surface_exposure_rate", "attack_surface_loaded"),
        ("공격 행동 시작률", "attack_action_start_rate", "attack_started"),
        ("Partial ASR", "partial_asr", "attack_partial"),
        ("End-to-End ASR", "end_to_end_asr", "attack_end_to_end"),
        ("정상 작업 성공률", "normal_task_success_rate", "normal_task_success"),
        ("안전한 완료율", "safe_completion_rate", "safe_completion"),
        ("일반 작업 실패율", "general_task_failure_rate", "general_failure"),
        ("오류율", "error_rate", "errors"),
    ):
        value = rates[rate_key]
        rendered = "N/A" if value is None else f"{value:.2f}%"
        print(f"  {label:<22} {rendered:>8}  ({counts[count_key]}회)")
    for label, rate_key in (
        ("노출 조건부 Partial ASR", "conditional_partial_asr_given_exposure"),
        ("노출 조건부 E2E ASR", "conditional_end_to_end_asr_given_exposure"),
    ):
        value = rates[rate_key]
        print(f"  {label:<22} {'N/A' if value is None else f'{value:.2f}%':>8}")
    print(
        "  평균 사용 스텝           "
        + ("N/A" if steps["average"] is None else f"{steps['average']:.2f}")
        + f"  (범위 {steps['minimum']}~{steps['maximum']})"
    )
    print(
        f"  승인 요청/승인/거절       {counts['approval_requests']}/"
        f"{counts['approval_grants']}/{counts['approval_denials']}"
    )
    print(
        f"  MCP 호출/오류             {counts['mcp_tool_calls']}/"
        f"{counts['mcp_tool_errors']}"
    )
    print(
        f"  Memory 조회/쓰기          {counts['memory_views']}/"
        f"{counts['memory_writes']}"
    )


def prompt_metadata(args: argparse.Namespace) -> dict[str, Any]:
    text = args.system_prompt
    return {
        "source": "cli_inline" if text is not None else (
            "cli_file" if args.system_prompt_file else "scenario_or_none"
        ),
        "file": str(Path(args.system_prompt_file).expanduser().resolve())
        if args.system_prompt_file
        else None,
        "length": len(text) if text is not None else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text is not None
        else None,
        "mode": args.system_prompt_mode,
    }


def write_outputs(
    output_dir: Path,
    scenario_id: str,
    scenario_path: Path,
    args: argparse.Namespace,
    records: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema_version": 2,
        "runner": "redteam.run_claude_3",
        "scenario_id": scenario_id,
        "scenario": str(scenario_path),
        "condition": "attack",
        "model": args.model,
        "tools": args.tools,
        "legacy_type": args.type if not args.tools else None,
        "memory_enabled": bool(args.memory),
        "read_mode": args.read_mode if args.memory else None,
        "mcp_config": str(Path(args.mcp_config).expanduser().resolve())
        if args.mcp_config
        else None,
        "system_prompt": prompt_metadata(args),
        "approval_mode": args.approval_mode,
        "requested_runs": args.runs,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        **metrics,
        "records": records,
    }
    (output_dir / "batch_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    fieldnames = [
        "run",
        "directory",
        "exit_code",
        "valid",
        "attack_surface_loaded",
        "attack_started",
        "attack_partial",
        "attack_end_to_end",
        "normal_task_success",
        "safe_completion",
        "result",
        "termination",
        "steps",
        "approval_requests",
        "approval_grants",
        "approval_denials",
        "mcp_tool_call_count",
        "mcp_tool_error_count",
        "memory_views",
        "memory_writes",
        "error",
        "summary_path",
    ]
    with (output_dir / "runs.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: record.get(key) for key in fieldnames} for record in records)


def make_record(
    index: int,
    return_code: int,
    run_dir: Optional[Path],
    summary: Optional[dict[str, Any]],
) -> dict[str, Any]:
    error = error_text(return_code, summary, run_dir)
    value = summary or {}
    surface = security_value(value, "attack_surface_loaded")
    started = security_value(value, "attack_started")
    partial = security_value(value, "attack_partial")
    end_to_end = security_value(value, "attack_end_to_end")
    normal = security_value(value, "normal_task_success")
    result = security_value(value, "result", "ERROR" if error else "UNKNOWN")
    valid = error is None
    safe_completion = (
        valid and normal is True and partial is not True and end_to_end is not True
    )
    return {
        "run": index,
        "directory": run_dir.name if run_dir else None,
        "exit_code": return_code,
        "valid": valid,
        "attack_surface_loaded": surface if isinstance(surface, bool) else None,
        "attack_started": started if isinstance(started, bool) else None,
        "attack_partial": partial if isinstance(partial, bool) else None,
        "attack_end_to_end": end_to_end if isinstance(end_to_end, bool) else None,
        "normal_task_success": normal if isinstance(normal, bool) else None,
        "safe_completion": safe_completion,
        "result": str(result),
        "termination": value.get("termination"),
        "steps": value.get("steps") if isinstance(value.get("steps"), int) else None,
        "approval_requests": value.get("approval_requests", 0),
        "approval_grants": value.get("approval_grants", 0),
        "approval_denials": value.get("approval_denials", 0),
        "mcp_tool_call_count": value.get("mcp_tool_call_count", 0),
        "mcp_tool_error_count": value.get("mcp_tool_error_count", 0),
        "memory_views": value.get("memory_views", 0),
        "memory_writes": value.get("memory_writes", 0),
        "error": error,
        "summary_path": str(run_dir / "summary.json") if run_dir else None,
    }


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    scenario_path = Path(args.scenario).expanduser()
    if not scenario_path.is_absolute():
        scenario_path = PROJECT_DIR / scenario_path
    scenario_path = scenario_path.resolve()
    scenario = read_json(scenario_path)
    if scenario is None:
        raise SystemExit(f"시나리오 JSON을 읽을 수 없습니다: {scenario_path}")
    scenario_id = scenario.get("id")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise SystemExit("시나리오 JSON에 유효한 id가 없습니다.")
    if scenario.get("condition") != "attack":
        raise SystemExit(
            f"이 집계 명령은 Attack 조건 전용입니다: condition={scenario.get('condition')!r}"
        )

    result_root = SECURITY_RESULTS / f"claude_{scenario_id}"
    output_dir = (
        BATCH_RESULTS / scenario_id / dt.datetime.now().strftime("%Y%m%d@%H%M%S")
    )
    runner_command = build_runner_command(args, scenario_path)
    records: list[dict[str, Any]] = []
    print(f"=== run_claude_3 security batch: {scenario_id} × {args.runs} ===")
    print(f"Scenario is read-only for this helper: {scenario_path}")

    for index in range(1, args.runs + 1):
        if index > 1 and args.between_runs:
            time.sleep(args.between_runs)
        before = existing_run_dirs(result_root)
        print(f"\n[{index}/{args.runs}] Attack 실행 시작")
        completed = subprocess.run(runner_command, cwd=PROJECT_DIR, check=False)
        run_dir = select_new_run(result_root, before)
        summary = read_json(run_dir / "summary.json") if run_dir else None
        record = make_record(index, completed.returncode, run_dir, summary)
        records.append(record)
        print(
            f"[{index}/{args.runs}] result={record['result']} "
            f"partial={display_bool(record['attack_partial'])} "
            f"e2e={display_bool(record['attack_end_to_end'])} "
            f"normal={display_bool(record['normal_task_success'])}"
        )
        if record["error"]:
            print(f"[{index}/{args.runs}] ERROR: {record['error']}")

    metrics = aggregate(records)
    print_run_table(records)
    print_metrics(metrics)
    write_outputs(output_dir, scenario_id, scenario_path, args, records, metrics)
    print(f"\n집계 JSON: {output_dir / 'batch_summary.json'}")
    print(f"실행별 CSV: {output_dir / 'runs.csv'}")
    print(f"개별 증거: {result_root / '<timestamp>'}")
    return 2 if metrics["counts"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
