#!/usr/bin/env python3
"""
F-2 업스트림 무패치 재현 (적대적 리뷰 지적 ① 대응)
=====================================================
지적: "B1 은 DesktopEnv 를 우회했고 B2a/B2b 는 커스텀 러너다.
       업스트림 파이프라인(get_vm_file → cache_dir → check_python_file_by_test_suite)을
       한 줄도 실행하지 않았다. 벤더 1순위 반박은 '네 하네스가 한 짓이다'."

이 스크립트는 **깨끗한 xlang-ai/OSWorld 클론**에서 실행되며,
`DesktopEnv.reset()` → `DesktopEnv.step()` → `DesktopEnv.evaluate()` 전 경로를
업스트림 코드 그대로 태운다. 패치 0줄.

모델만 스텁이다 — `env.step()` 은 에이전트가 낸 액션 문자열을 게스트에서 실행하는
바로 그 경로이므로, 스텁이 내는 액션은 실제 에이전트 출력과 동일한 경로를 지난다.
"에이전트가 그 파일을 쓸 수 있다"는 별도로 B2a/B2b 가 실증했다.

전제
  - 깨끗한 클론:  git clone --depth 1 https://github.com/xlang-ai/OSWorld.git ~/osworld-upstream
  - **ASCII 경로에 둘 것** (비ASCII 경로는 provider.start_emulator 무한루프 버그를 유발)
  - VM 이 실행 중이거나 vmrun 으로 시작 가능
  - 의존성: 기존 포크의 venv 파이썬을 그대로 써도 된다 (서드파티 라이브러리만 제공)

사용법 (맥에서)
  cd ~/osworld-upstream
  VMX=$(vmrun list | tail -1)
  PYTHONPATH=. <포크venv경로>/bin/python f2_upstream_verify.py --path_to_vm "$VMX" --snapshot init_state

수행: 카나리 파일 생성만. 네트워크 통신·지속성 없음.
⚠ 본인 소유 랩에서 책임공개 증거 수집 목적으로만 사용할 것.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

TASK_REL = "evaluation_examples/examples/multi_apps/9219480b-3aed-47fc-8bac-d2cffc5849f7.json"
CANARY = "/tmp/f2_upstream_CANARY"
GUEST_FILE = "/home/user/Desktop/tetris/settings.py"


def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "(실패)"


def sha256(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return "(없음)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path_to_vm", required=True,
                    help="vmrun list 출력 문자열을 그대로 넣을 것 (유니코드 정규화 문제 회피)")
    ap.add_argument("--snapshot", default="init_state")
    args = ap.parse_args()

    if not os.path.isfile(TASK_REL):
        sys.exit(f"태스크 JSON 없음: {TASK_REL}\n깨끗한 OSWorld 클론 루트에서 실행하라.")

    # ── 0. 실행 주체가 정말 업스트림 코드인지 증명 ───────────────────────
    print("=" * 70)
    print("[0] 무결성 / 출처 확인")
    print(f"    cwd                : {os.getcwd()}")
    print(f"    git HEAD           : {sh('git rev-parse HEAD')}")
    print(f"    git remote origin  : {sh('git remote get-url origin')}")
    print(f"    git status(변경)   : {sh('git status --porcelain | head -20') or '(clean)'}")
    print(f"    vscode.py sha256   : {sha256('desktop_env/evaluators/metrics/vscode.py')}")
    print(f"    file.py    sha256  : {sha256('desktop_env/evaluators/getters/file.py')}")
    print(f"    task json  sha256  : {sha256(TASK_REL)}")

    from desktop_env.desktop_env import DesktopEnv
    import desktop_env.desktop_env as de_mod
    import desktop_env.evaluators.metrics.vscode as vs_mod
    print(f"    로드된 desktop_env : {de_mod.__file__}")
    print(f"    로드된 metrics/vscode: {vs_mod.__file__}")
    print(f"    python             : {sys.executable}")

    task = json.load(open(TASK_REL, encoding="utf-8"))
    print(f"\n[태스크] {task['id']}")
    print(f"[지시문] {task.get('instruction','')[:110]}...")
    print(f"[evaluator] func={task['evaluator']['func']}  "
          f"result={task['evaluator']['result']['type']}  "
          f"expected={task['evaluator']['expected']['type']}")

    if os.path.exists(CANARY):
        os.remove(CANARY)
    print(f"\n[1] 호스트 카나리 사전 상태: {os.path.exists(CANARY)}")

    # ── 2. 업스트림 DesktopEnv ───────────────────────────────────────────
    print("\n[2] DesktopEnv 초기화 + reset (업스트림 코드)")
    env = DesktopEnv(
        path_to_vm=args.path_to_vm,
        action_space="pyautogui",
        snapshot_name=args.snapshot,
        require_a11y_tree=False,
    )
    env.reset(task_config=task)
    print(f"    cache_dir = {getattr(env, 'cache_dir', '?')}")

    # ── 3. env.step() — 에이전트 출력이 지나가는 바로 그 경로 ────────────
    # 실제 에이전트가 낼 법한 액션 하나. 스텁 모델이 이것을 냈다고 보면 된다.
    payload_lines = (
        "import pathlib, platform, os\n"
        f"pathlib.Path({CANARY!r}).write_text("
        "f'{platform.system()} {platform.machine()} pid={os.getpid()}\\n')\n"
    )
    action = (
        f"p = {GUEST_FILE!r}\n"
        "orig = open(p).read()\n"
        f"open(p, 'w').write({payload_lines!r} + orig)\n"
        "print('guest edited:', len(open(p).read()), 'bytes')\n"
    )
    print("\n[3] env.step() — 업스트림 step 으로 게스트 파일 편집")
    print("    (에이전트가 낸 액션 문자열이 지나가는 것과 동일한 경로)")
    env.step(action)

    # 게스트측에서 페이로드가 실행되지 않았는지 확인
    guest_probe = env.controller.get_file(CANARY)
    print(f"    게스트측 카나리: {'존재(!)' if guest_probe else '부재(정상)'}")

    # ── 4. env.evaluate() — 업스트림 채점 전 경로 ────────────────────────
    print("\n[4] env.evaluate() — get_vm_file → cache_dir → check_python_file_by_test_suite")
    score = env.evaluate()

    hit = os.path.exists(CANARY)
    print(f"\n[반환 score] {score}")
    print(f"[호스트 카나리] {hit}")
    if hit:
        print(f"[카나리 내용] {open(CANARY).read().strip()}")
        st = os.stat(CANARY)
        print(f"[카나리 mtime] {st.st_mtime}")

    cd = getattr(env, "cache_dir", None)
    if cd and os.path.isdir(cd):
        print(f"\n[cache_dir 내용] {cd}")
        for n in sorted(os.listdir(cd)):
            p = os.path.join(cd, n)
            print(f"    {n:40s} {os.path.getsize(p) if os.path.isfile(p) else '<dir>'}")
        pyc = os.path.join(cd, "__pycache__")
        if os.path.isdir(pyc):
            print(f"    __pycache__: {sorted(os.listdir(pyc))}")

    print("\n" + "=" * 70)
    if hit:
        print("판정: ★ 업스트림 무패치 파이프라인에서 재현됨")
        print("  · 깨끗한 xlang-ai/OSWorld 클론, git status clean")
        print("  · DesktopEnv.reset / step / evaluate 전부 업스트림 코드")
        print("  · 게스트에서 편집된 .py 가 호스트에서 실행됨")
        print("  → '커스텀 하네스가 한 짓' 반박 무효화")
    else:
        print("판정: ✗ 미재현 — 위 단계별 출력 확인")
    print("=" * 70)
    print("\n증거로 남길 것: 이 출력 전문, cache_dir 사본, git rev-parse HEAD")

    try:
        env.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
