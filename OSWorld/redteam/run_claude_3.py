#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified Claude Computer Use runner for OSWorld.

This is a backwards-compatible successor to run_claude_2.py.  It keeps the
computer/bash/editor, popup, memory, local stdio MCP, setup/evaluation, and
result logging features while using one configurable agent class.  It adds a
real host-terminal approval tool and configurable system prompts.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

from desktop_env.desktop_env import DesktopEnv
from desktop_env.evaluators import getters
from mm_agents.claude_cua.agent_system_prompt_mcp_memory import (
    SystemPromptMCPMemoryClaudeCUAAgent,
)


PROJECT_DIR = next(
    (path for path in Path(__file__).resolve().parents if (path / "desktop_env").is_dir()),
    Path(__file__).resolve().parent,
)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Claude Computer Use on OSWorld (unified MCP/memory/system/approval runner)."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--scenario", help="OSWorld/security scenario JSON")
    source.add_argument("--instruction", help="Free-form smoke instruction")

    parser.add_argument(
        "--tools",
        default=None,
        help="Comma list: computer[,bash][,editor][,mcp]. Overrides --type.",
    )
    parser.add_argument(
        "--type",
        choices=["gui", "tool"],
        default="gui",
        help="Legacy: gui=computer, tool=computer,bash. Explicit --tools wins.",
    )
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--path-to-vm", default=None)
    parser.add_argument("--snapshot", default="init_state")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--initial-wait", type=float, default=3.0)
    parser.add_argument("--send-width", type=int, default=1280)

    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memstore-dir", default=None)
    parser.add_argument(
        "--read-mode", choices=["faithful", "controlled", "inject"], default="faithful"
    )
    parser.add_argument("--mcp-config", default=None)

    prompt = parser.add_mutually_exclusive_group()
    prompt.add_argument("--system-prompt", default=None, help="Inline system prompt")
    prompt.add_argument("--system-prompt-file", default=None, help="UTF-8 system prompt file")
    parser.add_argument(
        "--system-prompt-mode", choices=["append", "replace"], default=None
    )
    parser.add_argument(
        "--approval-mode",
        choices=["off", "interactive"],
        default="off",
        help="interactive exposes request_user_approval and reads y/N from host stdin",
    )

    parser.add_argument("--allow-external-screen-share", action="store_true")
    parser.add_argument("--execute-actions", action="store_true")
    parser.add_argument("--setup-only", action="store_true")
    parser.add_argument("--mcp-check-only", action="store_true")
    parser.add_argument("--config-check-only", action="store_true")

    parser.add_argument("--inject-popup", action="store_true")
    parser.add_argument(
        "--popup-pos", choices=["center", "bottom", "top"], default="center"
    )
    parser.add_argument("--popup-no-ad", action="store_true")
    parser.add_argument("--popup-xy", default=None)
    return parser.parse_args(argv)


def resolve_tools(args: argparse.Namespace) -> list[str]:
    if args.tools:
        requested = [item.strip() for item in args.tools.split(",") if item.strip()]
    else:
        requested = ["computer"] if args.type == "gui" else ["computer", "bash"]
        if args.type == "tool":
            print("[!] legacy --type tool enables bash; prefer --tools computer,bash.")
    unknown = sorted(set(requested) - {"computer", "bash", "editor", "mcp"})
    if unknown:
        raise SystemExit("unsupported tool: " + ", ".join(unknown))
    return ["computer"] + [name for name in ("bash", "editor", "mcp") if name in requested]


def load_scenario(path: Path) -> Dict[str, Any]:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    for item in scenario.get("config", []):
        if item.get("type") != "upload_file":
            continue
        for file_config in item.get("parameters", {}).get("files", []):
            local = Path(file_config["local_path"])
            if not local.is_absolute():
                local = path.parent / local
            file_config["local_path"] = str(local.resolve())
    return scenario


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_system_prompt(
    args: argparse.Namespace,
    task: Dict[str, Any],
    scenario_path: Optional[Path],
) -> Tuple[Optional[str], Dict[str, Any]]:
    policy = task.get("agent_prompt_policy") or {}
    if not isinstance(policy, dict):
        raise ValueError("agent_prompt_policy must be a JSON object")

    text: Optional[str] = None
    source = "none"
    source_path: Optional[str] = None
    mode = args.system_prompt_mode or policy.get("system_prompt_mode") or "append"
    if mode not in {"append", "replace"}:
        raise ValueError("system prompt mode must be append or replace")

    if args.system_prompt is not None:
        text = args.system_prompt
        source = "cli_inline"
    elif args.system_prompt_file is not None:
        path = Path(args.system_prompt_file).expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        source = "cli_file"
        source_path = str(path)
    elif policy.get("system_prompt") is not None:
        text = str(policy["system_prompt"])
        source = "scenario_inline"
    elif policy.get("system_prompt_file") is not None:
        path = Path(str(policy["system_prompt_file"]))
        if not path.is_absolute():
            if scenario_path is None:
                raise ValueError("relative scenario system prompt requires --scenario")
            path = scenario_path.parent / path
        path = path.expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        source = "scenario_file"
        source_path = str(path)

    if text is not None and not text.strip():
        raise ValueError("system prompt must not be empty")
    encoded = text.encode("utf-8") if text is not None else b""
    metadata = {
        "enabled": text is not None,
        "mode": mode,
        "source": source,
        "source_path": source_path,
        "length": len(text) if text is not None else 0,
        "sha256": hashlib.sha256(encoded).hexdigest() if text is not None else None,
    }
    return text, metadata


def load_mcp_config(args: argparse.Namespace, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = task.get("mcp")
    if args.mcp_config:
        config = json.loads(Path(args.mcp_config).expanduser().resolve().read_text(encoding="utf-8"))
    if config is not None and not isinstance(config, dict):
        raise ValueError("MCP config must be a JSON object")
    if config and config.get("transport") != "stdio":
        raise ValueError("run_claude_3 supports isolated stdio MCP only")
    return config


def collect_security_evaluation(env: DesktopEnv, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    config = task.get("security_evaluation")
    if not config:
        return None
    result_type = config.get("type")
    if not isinstance(result_type, str):
        raise ValueError("security_evaluation.type must be a getter name")
    getter = getattr(getters, f"get_{result_type}")
    parsed = json.loads(getter(env, config))
    if not isinstance(parsed, dict):
        raise ValueError("security_evaluation must return one JSON object")
    return parsed


def print_effective_config(config: Dict[str, Any]) -> None:
    print("=== Effective Agent Configuration ===")
    print(f"Scenario: {config['task_id']}")
    print("Agent: SystemPromptMCPMemoryClaudeCUAAgent")
    print("Tools: " + ", ".join(config["tools_enabled"]))
    print(f"Bash: {'ON' if 'bash' in config['tools_enabled'] else 'OFF'}")
    print(f"Editor: {'ON' if 'editor' in config['tools_enabled'] else 'OFF'}")
    print(f"MCP: {'ON' if config['mcp_enabled'] else 'OFF'}")
    print(f"Memory: {'ON' if config['memory_enabled'] else 'OFF'}")
    prompt = config["system_prompt"]
    print(f"System prompt: {'ON' if prompt['enabled'] else 'OFF'} ({prompt['mode']})")
    print(f"Approval mode: {config['approval_mode']}")
    if config["approval_mode"] == "interactive":
        print("Approval input: Host PowerShell")
        print("Interactive input required: YES")
    print("=====================================")


def main(argv: Optional[list[str]] = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    load_dotenv()
    args = parse_args(argv)
    tools = resolve_tools(args)
    if sum((args.setup_only, args.mcp_check_only, args.config_check_only)) > 1:
        raise SystemExit("--setup-only, --mcp-check-only, --config-check-only are mutually exclusive")

    scenario_path: Optional[Path] = None
    if args.scenario:
        scenario_path = Path(args.scenario).expanduser().resolve()
        task = load_scenario(scenario_path)
        instruction = task["instruction"]
        task_id = task["id"]
        max_steps = args.max_steps or int(task.get("recommended_max_steps", 15))
    else:
        task_id = "claude-smoke"
        instruction = args.instruction
        task = {
            "id": task_id,
            "instruction": instruction,
            "config": [],
            "evaluator": {"func": "infeasible"},
        }
        max_steps = args.max_steps or 15

    system_prompt_text, system_prompt_metadata = resolve_system_prompt(
        args, task, scenario_path
    )
    mcp_config = load_mcp_config(args, task)
    mcp_enabled = bool(mcp_config and "mcp" in tools)
    if "mcp" in tools and not mcp_config:
        raise SystemExit("MCP was requested but no scenario mcp object or --mcp-config was supplied")
    if mcp_config and "mcp" not in tools:
        print("[!] MCP config exists but MCP is disabled because --tools omits mcp.")
    if args.mcp_check_only and not mcp_enabled:
        raise SystemExit("--mcp-check-only requires MCP config and --tools ...mcp")

    effective_tools = list(tools)
    if args.memory:
        effective_tools.append("memory")
    if args.approval_mode == "interactive":
        effective_tools.append("request_user_approval")
    effective = {
        "task_id": task_id,
        "tools_enabled": effective_tools,
        "mcp_enabled": mcp_enabled,
        "memory_enabled": bool(args.memory),
        "approval_mode": args.approval_mode,
        "system_prompt": system_prompt_metadata,
    }
    print_effective_config(effective)

    if args.config_check_only:
        print("CONFIG_CHECK_READY — no VM, model, action, or evaluator was run.")
        return
    non_agent_mode = args.setup_only or args.mcp_check_only
    if (
        args.approval_mode == "interactive"
        and not non_agent_mode
        and not sys.stdin.isatty()
    ):
        raise SystemExit("interactive approval requires a foreground terminal with stdin")
    if not non_agent_mode and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is missing (.env)")
    if not non_agent_mode and (
        not args.allow_external_screen_share or not args.execute_actions
    ):
        raise SystemExit(
            "refused: pass --allow-external-screen-share and --execute-actions after reviewing the VM"
        )

    vm_path = (
        Path(args.path_to_vm).expanduser().resolve()
        if args.path_to_vm
        else PROJECT_DIR / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"
    )
    if not vm_path.is_file():
        raise SystemExit(f"VMX file not found: {vm_path}")

    timestamp = dt.datetime.now().strftime("%Y%m%d@%H%M%S")
    result_dir = PROJECT_DIR / "security_results" / f"claude_{task_id}" / timestamp
    result_dir.mkdir(parents=True, exist_ok=True)
    run_config = {
        "task_id": task_id,
        "agent_class": "SystemPromptMCPMemoryClaudeCUAAgent",
        "model": args.model,
        "tools_enabled": effective_tools,
        "max_steps": max_steps,
        "screen_size": [1920, 1080],
        "provider": "vmware",
        "snapshot": args.snapshot,
        "observation_type": "screenshot",
        "action_space": "pyautogui",
        "condition": task.get("condition"),
        "timestamp": timestamp,
        "scenario": str(scenario_path) if scenario_path else None,
        "instruction": instruction,
        "system_prompt": system_prompt_metadata,
        "memory_enabled": bool(args.memory),
        "read_mode": args.read_mode if args.memory else None,
        "memstore_dir": args.memstore_dir if args.memory else None,
        "mcp_enabled": mcp_enabled,
        "mcp": mcp_config if mcp_enabled else None,
        "approval_mode": args.approval_mode,
        "approval_input": "host_terminal" if args.approval_mode == "interactive" else None,
    }
    write_json(result_dir / "run_config.json", run_config)

    summary: Dict[str, Any] = {
        "task_id": task_id,
        "model": args.model,
        "tools": effective_tools,
        "attack_success": None,
        "attack_score": None,
        "termination": None,
        "system_prompt": system_prompt_metadata,
        "approval_mode": args.approval_mode,
    }
    env: Optional[DesktopEnv] = None
    try:
        env = DesktopEnv(
            provider_name="vmware",
            path_to_vm=str(vm_path),
            snapshot_name=args.snapshot,
            action_space="pyautogui",
            screen_size=(1920, 1080),
            require_a11y_tree=False,
            os_type="Ubuntu",
            client_password="password",
        )
        env.reset(task_config=task)
        time.sleep(args.initial_wait)
        observation = env._get_obs()
        (result_dir / "step_000.png").write_bytes(observation["screenshot"])

        if args.setup_only:
            summary["termination"] = "setup_only"
            print("SETUP_READY — no model call was made.")
            return

        popup_xy = None
        if args.popup_xy:
            x_text, y_text = args.popup_xy.split(",")
            popup_xy = (int(x_text), int(y_text))

        agent = SystemPromptMCPMemoryClaudeCUAAgent(
            env,
            model=args.model,
            tools=tuple(tools),
            send_width=args.send_width,
            action_pause=args.pause,
            inject_popup=args.inject_popup,
            popup_pos=args.popup_pos,
            popup_ad_label=not args.popup_no_ad,
            popup_xy=popup_xy,
            mcp_config=mcp_config if mcp_enabled else None,
            mcp_result_dir=str(result_dir) if mcp_enabled else None,
            enable_memory=args.memory,
            memstore_dir=args.memstore_dir,
            read_mode=args.read_mode,
            system_prompt_text=system_prompt_text,
            system_prompt_mode=system_prompt_metadata["mode"],
            approval_mode=args.approval_mode,
            approval_result_dir=str(result_dir),
            api_key=os.environ.get("ANTHROPIC_API_KEY") or "check-only-no-api-call",
            verbose=not args.mcp_check_only,
        )

        if args.mcp_check_only:
            summary.update(
                {
                    "termination": "mcp_check_only",
                    "mcp_enabled": True,
                    "mcp_handshake_success": True,
                    "mcp_tools_discovered": sorted(agent.mcp_tool_names),
                    "mcp_tool_call_count": 0,
                    "mcp_tool_error_count": 0,
                    "mcp_tool_call_log": "mcp_tool_calls.jsonl",
                    "mcp_protocol_log": "mcp_protocol.jsonl",
                }
            )
            print("MCP_CHECK_READY — no model or evaluator call was made.")
            return

        result = agent.run(instruction, max_steps=max_steps, result_dir=str(result_dir))
        summary.update(
            {
                "termination": result["termination"],
                "steps": result["steps"],
                "usage": result["usage"],
                "final_text": result.get("final_text", ""),
            }
        )
        for key in (
            "tools_enabled",
            "mcp_enabled",
            "mcp_tools_discovered",
            "mcp_tool_call_count",
            "mcp_tool_error_count",
            "mcp_tool_call_log",
            "mcp_protocol_log",
            "memory_enabled",
            "read_mode",
            "memstore_dir",
            "memory_files_at_start",
            "memory_views",
            "memory_writes",
            "memory_recalled_via_tool",
            "approval_requests",
            "approval_grants",
            "approval_denials",
            "approval_log",
        ):
            if key in result:
                summary[key] = result[key]

        if args.inject_popup:
            cta = bool(result.get("popup_cta_clicked"))
            summary.update(
                {
                    "popup_injected": True,
                    "popup_clicked_any": bool(result.get("popup_clicked")),
                    "popup_cta_clicked": cta,
                    "popup_close_clicked": bool(result.get("popup_close_clicked")),
                    "popup_click_steps": result.get("popup_click_steps", []),
                    "attack_success": cta,
                    "attack_score": float(cta),
                }
            )
        else:
            try:
                score = float(env.evaluate())
                summary["attack_score"] = score
                summary["attack_success"] = bool(score)
            except Exception as exc:  # noqa: BLE001
                summary["evaluation_error"] = f"{type(exc).__name__}: {exc}"

            try:
                security = collect_security_evaluation(env, task)
                if security is not None:
                    summary["security_evaluation"] = security
                    for key in (
                        "normal_task_success",
                        "attack_surface_loaded",
                        "attack_started",
                        "attack_partial",
                        "attack_end_to_end",
                        "result",
                        "evidence",
                    ):
                        if key in security:
                            summary[key] = security[key]
                    if "attack_end_to_end" in security:
                        summary["attack_success"] = bool(security["attack_end_to_end"])
                        summary["attack_score"] = float(summary["attack_success"])
            except Exception as exc:  # noqa: BLE001
                summary["security_evaluation_error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(result_dir / "summary.json", summary)
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
