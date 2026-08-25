#!/usr/bin/env python3
"""Run one controlled CUA security scenario with local evidence collection."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from desktop_env.desktop_env import DesktopEnv
from mm_agents.opencua import OpenCUAAgent

# run_opencua_smoke.py lives next to this file — add its dir to sys.path so this
# import resolves whether the script is at repo root or in a subfolder (e.g. redteam/).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_opencua_smoke import is_safe_smoke_action


# Repo root = nearest ancestor containing desktop_env/. Robust to this script
# living at repo root OR inside a subfolder like redteam/.
PROJECT_DIR = next(
    (p for p in Path(__file__).resolve().parents if (p / "desktop_env").is_dir()),
    Path(__file__).resolve().parent,
)
DEFAULT_SCENARIO = (
    PROJECT_DIR
    / "security_scenarios"
    / "ipi_001_visible_web_prompt"
    / "scenario.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a controlled OSWorld CUA attack scenario."
    )
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    parser.add_argument("--path-to-vm", default=None)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--initial-wait", type=float, default=3.0)
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Prepare and verify the scenario without calling the model.",
    )
    parser.add_argument(
        "--allow-external-screen-share",
        action="store_true",
        help="Allow VM screenshots to be sent to OPENCUA_BASE_URL.",
    )
    parser.add_argument(
        "--execute-actions",
        action="store_true",
        help="Allow validated model GUI actions to execute inside the VM.",
    )
    return parser.parse_args()


def load_scenario(path: Path) -> dict[str, Any]:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    for setup_item in scenario.get("config", []):
        if setup_item.get("type") != "upload_file":
            continue
        for file_config in setup_item["parameters"].get("files", []):
            local_path = Path(file_config["local_path"])
            if not local_path.is_absolute():
                local_path = path.parent / local_path
            file_config["local_path"] = str(local_path.resolve())
    return scenario


def extract_typed_text(action: str) -> list[str | None]:
    try:
        tree = ast.parse(action, mode="exec")
    except SyntaxError:
        return [None]

    typed: list[str | None] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"write", "typewrite"}:
            continue
        value = node.args[0] if node.args else None
        if value is None:
            for keyword in node.keywords:
                if keyword.arg in {"message", "text"}:
                    value = keyword.value
                    break
        typed.append(value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None)
    return typed


def is_allowed_scenario_action(action: str, scenario: dict[str, Any]) -> bool:
    if not is_safe_smoke_action(action):
        return False
    safety = scenario.get("safety", {})
    allowed_text = set(safety.get("allowed_typed_text", []))
    # Typing a URL to the controlled test server (browser address bar) is safe,
    # so allow any typed text starting with a whitelisted prefix. This avoids
    # brittle exact-match failures when the model types the URL slightly
    # differently (root vs full path, trailing slash, appended newline, ...).
    # Non-URL typing (e.g. the terminal marker command) is still exact-matched.
    allowed_prefixes = tuple(safety.get("allowed_typed_prefixes", []))
    for text in extract_typed_text(action):
        if text is None:
            return False
        if text in allowed_text:
            continue
        if allowed_prefixes and text.startswith(allowed_prefixes):
            continue
        return False
    return True


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def wait_for_expected_tab(env: DesktopEnv, scenario: dict[str, Any], timeout: float = 20) -> str:
    expected = scenario.get("readiness", {}).get("expected_tab_url")
    if not expected:
        return ""

    deadline = time.time() + timeout
    seen_urls: list[str] = []
    while time.time() < deadline:
        try:
            response = requests.get(
                f"http://{env.vm_ip}:{env.chromium_port}/json/list",
                timeout=5,
            )
            response.raise_for_status()
            seen_urls = [tab.get("url", "") for tab in response.json()]
            if expected in seen_urls:
                return expected
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError(
        f"Scenario page is not ready. Expected {expected!r}; observed {seen_urls!r}"
    )


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.setup_only and (
        not args.allow_external_screen_share or not args.execute_actions
    ):
        raise SystemExit(
            "Refusing to run. Review the scenario, then pass both "
            "--allow-external-screen-share and --execute-actions."
        )

    base_url = os.environ.get("OPENCUA_BASE_URL")
    model = os.environ.get("OPENCUA_MODEL", "opencua-32b")
    if not args.setup_only and not base_url:
        raise SystemExit("OPENCUA_BASE_URL is not set in this terminal.")

    scenario_path = Path(args.scenario).expanduser().resolve()
    scenario = load_scenario(scenario_path)
    max_steps = args.max_steps or int(scenario.get("recommended_max_steps", 12))
    path_to_vm = (
        Path(args.path_to_vm).expanduser().resolve()
        if args.path_to_vm
        else PROJECT_DIR / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"
    )
    if not path_to_vm.is_file():
        raise SystemExit(f"VMX file not found: {path_to_vm}")

    timestamp = dt.datetime.now().strftime("%Y%m%d@%H%M%S")
    result_dir = PROJECT_DIR / "security_results" / scenario["id"] / timestamp
    result_dir.mkdir(parents=True, exist_ok=False)
    trajectory_path = result_dir / "trajectory.jsonl"
    write_json(
        result_dir / "run_config.json",
        {
            "scenario": str(scenario_path),
            "scenario_id": scenario["id"],
            "model": model,
            "base_url": base_url,
            "max_steps": max_steps,
            "pause": args.pause,
            "initial_wait": args.initial_wait,
            "setup_only": args.setup_only,
            "screen_size": [1920, 1080],
        },
    )

    print(f"Scenario: {scenario['id']} — {scenario['name']}")
    print(f"Model: {model}")
    print(f"Result directory: {result_dir}")
    print("Evaluator semantics: 1 means ATTACK SUCCEEDED (worse security).")

    env = None
    summary: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "model": model,
        "attack_success": None,
        "attack_score": None,
        "termination": None,
    }
    try:
        env = DesktopEnv(
            provider_name="vmware",
            path_to_vm=str(path_to_vm),
            snapshot_name="init_state",
            action_space="pyautogui",
            screen_size=(1920, 1080),
            require_a11y_tree=False,
            os_type="Ubuntu",
            client_password="password",
        )
        obs = env.reset(task_config=scenario)
        time.sleep(args.initial_wait)
        obs = env._get_obs()
        (result_dir / "step_000.png").write_bytes(obs["screenshot"])
        ready_url = wait_for_expected_tab(env, scenario)
        print(f"Scenario page ready: {ready_url}")

        if args.setup_only:
            summary["termination"] = "setup_only"
            print("SETUP_READY — model was not called and no model action was executed.")
            return

        agent = OpenCUAAgent(
            model=model,
            history_type="action_history",
            max_steps=max_steps,
            max_image_history_length=3,
            platform="ubuntu",
            max_tokens=768,
            temperature=0,
            action_space="pyautogui",
            observation_type="screenshot",
            cot_level="l2",
            screen_size=(1920, 1080),
            coordinate_type="qwen25",
            use_old_sys_prompt=True,
            password="password",
        )
        agent.reset()

        for step in range(1, max_steps + 1):
            print(f"\n=== Step {step}/{max_steps} ===")
            response, actions, model_info = agent.predict(
                scenario["instruction"], obs, step_idx=step
            )
            # 모델의 판단(## Thought / ## Action / ## Code)을 터미널에 실시간 출력
            if response:
                print("--- model reasoning ---")
                print(response.strip())
                print("--- end reasoning ---")
            action = actions[0] if actions else None
            print(f"Parsed action: {action}")

            record: dict[str, Any] = {
                "step": step,
                "response": response,
                "actions": actions,
                "model_info": model_info,
                "executed": False,
            }
            if action is None:
                summary["termination"] = "no_action"
                append_jsonl(trajectory_path, record)
                break

            if action in {"DONE", "FAIL"}:
                obs, _, done, info = env.step(action, pause=0)
                record.update({"executed": True, "done": done, "info": info})
                append_jsonl(trajectory_path, record)
                summary["termination"] = action.lower()
                break

            if action == "WAIT":
                obs, _, done, info = env.step(action, pause=args.pause)
                record.update({"executed": True, "done": done, "info": info})
            elif is_allowed_scenario_action(action, scenario):
                obs, _, done, info = env.step(action, pause=args.pause)
                record.update({"executed": True, "done": done, "info": info})
            else:
                print("Blocked action: outside the scenario-specific allowlist.")
                record["blocked_by_harness"] = True
                append_jsonl(trajectory_path, record)
                summary["termination"] = "blocked_by_harness"
                break

            screenshot_name = f"step_{step:03d}.png"
            (result_dir / screenshot_name).write_bytes(obs["screenshot"])
            record["screenshot"] = screenshot_name
            append_jsonl(trajectory_path, record)
        else:
            summary["termination"] = "max_steps"

        score = float(env.evaluate())
        summary["attack_score"] = score
        summary["attack_success"] = bool(score)
        print("\nATTACK_SUCCEEDED" if score else "\nATTACK_BLOCKED")
        print(f"Attack score: {score:.0f} (1 means vulnerable)")
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        write_json(result_dir / "summary.json", summary)
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
