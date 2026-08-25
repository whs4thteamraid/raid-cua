#!/usr/bin/env python3
"""
watch_dev.py — OSWorld VM을 '계속 켜둔 채' 실시간으로 관찰/조작하는 개발용 스크립트.

기존 Ubuntu VM 쓰던 방식처럼:
  - VM을 한 번만 켜고 (init_state 스냅샷으로 1회 초기화)
  - 이후로는 껐다 켜지 않음 (close/revert 안 함)
  - 명령을 하나씩 넣으면서 Fusion 창으로 실시간으로 지켜봄
  - 매 명령마다 스크린샷을 ./cache/watch 에 저장해서 파일로도 확인 가능

사용법:
    python watch_dev.py

대화형 프롬프트 명령:
    <파이썬/파이오토구이 코드>   예: pyautogui.click(960, 540)
    shot                         현재 화면만 스크린샷으로 저장
    ip                           VM IP 출력 (VNC/curl 확인용)
    quit                         VM은 켜둔 채 스크립트만 종료 (다음 실행 빠름)
    close                        VM 전원까지 끔
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from desktop_env.desktop_env import DesktopEnv

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_VMX = PROJECT_DIR / "vmware_vm_data" / "Ubuntu0" / "Ubuntu0.vmx"
SHOT_DIR = PROJECT_DIR / "cache" / "watch"


def save_shot(obs, idx):
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"shot_{idx:03d}.png"
    data = obs.get("screenshot") if isinstance(obs, dict) else None
    if data:
        path.write_bytes(data)
        print(f"  📸 저장: {path}")
    else:
        print("  ⚠️  스크린샷을 받지 못했습니다 (게스트 5000 서버 확인 필요)")
    return path


def main():
    vmx = os.environ.get("OSWORLD_VMX", str(DEFAULT_VMX))
    if not Path(vmx).is_file():
        raise SystemExit(f"VMX 파일을 찾을 수 없습니다: {vmx}")

    print("=" * 60)
    print("OSWorld 관찰 모드 — VM을 계속 켜둔 채로 조작합니다.")
    print(f"VM: {vmx}")
    print("처음 한 번만 init_state 스냅샷으로 초기화하고 부팅합니다 (~1-2분).")
    print("=" * 60)

    # require_a11y_tree=False → 접근성 트리 수집을 건너뛰어 매 step이 더 빠름
    env = DesktopEnv(
        provider_name="vmware",
        path_to_vm=vmx,
        snapshot_name="init_state",
        action_space="pyautogui",
        screen_size=(1920, 1080),
        require_a11y_tree=False,
        headless=False,          # Fusion 창을 띄워서 눈으로 관찰
        os_type="Ubuntu",
        client_password="password",
    )

    # config=[] 인 no-op 태스크로 1회만 초기화. 이후로는 reset을 다시 부르지 않으므로
    # VM은 껐다 켜지지 않고 계속 유지됩니다.
    noop_task = {
        "id": "watch-dev",
        "instruction": "interactive watch mode",
        "config": [],
        "evaluator": {"func": "infeasible"},
    }
    print("\n환경 초기화 중... (여기서만 기다리면 됩니다)")
    obs = env.reset(task_config=noop_task)
    print("✅ 준비 완료. 이제 VM은 계속 켜져 있습니다.")
    print(f"   VM IP: {getattr(env, 'vm_ip', '?')}  (VNC/스크린샷 확인용)")
    save_shot(obs, 0)

    idx = 1
    leave_running = True
    try:
        while True:
            try:
                cmd = input("\nosworld> ").strip()
            except EOFError:
                break
            if not cmd:
                continue
            if cmd == "quit":
                leave_running = True
                break
            if cmd == "close":
                leave_running = False
                break
            if cmd == "ip":
                print(f"  VM IP: {getattr(env, 'vm_ip', '?')}")
                continue
            if cmd == "shot":
                obs = env._get_obs()
                save_shot(obs, idx)
                idx += 1
                continue

            # 그 외에는 pyautogui/파이썬 명령으로 실행
            try:
                obs, reward, done, info = env.step(cmd, pause=1)
                print(f"  실행됨. done={done} info={info}")
                save_shot(obs, idx)
                idx += 1
            except Exception as e:
                print(f"  ❌ 실행 오류: {e}")
    finally:
        if leave_running:
            print("\nVM은 켜둔 채 종료합니다. (다음 실행이 빨라집니다)")
        else:
            print("\nVM 전원을 끕니다...")
            env.close()
        print("끝.")


if __name__ == "__main__":
    main()
