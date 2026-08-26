#!/usr/bin/env python3
"""Minimal, guarded OpenCUA-to-OSWorld connection test."""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path

from dotenv import load_dotenv

from desktop_env.desktop_env import DesktopEnv
from mm_agents.opencua import OpenCUAAgent


SAFE_PYAUTOGUI_CALLS = {
    "click",
    "doubleClick",
    "rightClick",
    "moveTo",
    "dragTo",
    "write",
    "typewrite",
    "press",
    "hotkey",
    "scroll",
}


def _is_literal_arg(value: ast.AST) -> bool:
    """Accept literal constants, and unary +/- on a numeric constant.

    In Python's AST a negative number such as ``-6`` is not an ``ast.Constant``
    but ``UnaryOp(USub, Constant(6))``. Without this, any pyautogui call with a
    negative argument (e.g. ``scroll(-6)`` for scrolling down, or a negative
    coordinate) would be rejected as unsafe even though it is a plain literal.
    """
    if isinstance(value, ast.Constant):
        return True
    if (
        isinstance(value, ast.UnaryOp)
        and isinstance(value.op, (ast.UAdd, ast.USub))
        and isinstance(value.operand, ast.Constant)
        and isinstance(value.operand.value, (int, float))
    ):
        return True
    # A literal list/tuple of literals, e.g. hotkey(['ctrl', 'alt', 't']).
    # The model sometimes passes key combos as a single list argument instead
    # of separate positional args; that is still a plain literal and safe.
    if isinstance(value, (ast.List, ast.Tuple)):
        return all(_is_literal_arg(element) for element in value.elts)
    return False


def is_safe_smoke_action(action: str) -> bool:
    """Allow only simple pyautogui calls with literal arguments."""
    try:
        tree = ast.parse(action, mode="exec")
    except SyntaxError:
        return False

    if not 1 <= len(tree.body) <= 3:
        return False

    for statement in tree.body:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            return False
        call = statement.value
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "pyautogui"
            and call.func.attr in SAFE_PYAUTOGUI_CALLS
        ):
            return False
        values = list(call.args) + [keyword.value for keyword in call.keywords]
        if not all(_is_literal_arg(value) for value in values):
            return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send OSWorld screenshots to OpenCUA and execute guarded GUI actions."
    )
    parser.add_argument(
        "--allow-external-screen-share",
        action="store_true",
        help="Confirm that VM screenshots may be sent to OPENCUA_BASE_URL.",
    )
    parser.add_argument(
        "--execute-actions",
        action="store_true",
        help="Confirm that validated model actions may run inside the VM.",
    )
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument(
        "--task",
        default=(
            "Move the mouse pointer to the center of the desktop, right-click once, "
            "and then terminate successfully."
        ),
    )
    parser.add_argument("--path-to-vm", default=None)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if not args.allow_external_screen_share or not args.execute_actions:
        raise SystemExit(
            "Refusing to run. Pass both --allow-external-screen-share and "
            "--execute-actions after reviewing the VM screen."
        )

    base_url = os.environ.get("OPENCUA_BASE_URL")
    model = os.environ.get("OPENCUA_MODEL", "opencua-32b")
    if not base_url:
        raise SystemExit("OPENCUA_BASE_URL is not set in this terminal.")

    project_dir = next(
        (p for p in Path(__file__).resolve().parents if (p / "desktop_env").is_dir()),
        Path(__file__).resolve().parent,
    )
    path_to_vm = Path(args.path_to_vm).expanduser() if args.path_to_vm else (
        project_dir / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"
    )
    if not path_to_vm.is_file():
        raise SystemExit(f"VMX file not found: {path_to_vm}")

    task = {
        "id": "opencua-osworld-smoke-test",
        "instruction": args.task,
        "config": [],
        "evaluator": {"func": "infeasible"},
    }

    print(f"OpenCUA endpoint: {base_url}")
    print(f"Model: {model}")
    print(f"VM: {path_to_vm}")
    print("The VM will revert to the init_state snapshot before the test.")

    env = None
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
        agent = OpenCUAAgent(
            model=model,
            history_type="action_history",
            max_steps=args.max_steps,
            max_image_history_length=3,
            platform="ubuntu",
            max_tokens=512,
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
        obs = env.reset(task_config=task)

        for step in range(1, args.max_steps + 1):
            print(f"\n=== Step {step}/{args.max_steps} ===")
            response, actions, _ = agent.predict(args.task, obs, step_idx=step)
            print(response)

            if not actions:
                print("No action returned; stopping.")
                break

            action = actions[0]
            print(f"Parsed action: {action}")
            if action in {"DONE", "FAIL"}:
                print(f"Model terminated with: {action}")
                break
            if action == "WAIT":
                obs, _, _, _ = env.step(action, pause=args.pause)
                continue
            if not is_safe_smoke_action(action):
                print("Blocked action: it is outside the smoke-test pyautogui allowlist.")
                break

            obs, _, done, info = env.step(action, pause=args.pause)
            print(f"Executed safely. done={done}, info={info}")
            if done:
                break
    finally:
        if env is not None:
            env.close()


if __name__ == "__main__":
    main()
