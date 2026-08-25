# Claude Computer Use (유형2) on OSWorld — 작업 요약 / 핸드오프

*OSWorld-audit 에 Claude Computer Use 를 유형1/2 전환 가능하게 붙인 작업 정리 (2026-08-18).*

## TL;DR
- **기존 코드는 안 건드림.** `mm_agents/anthropic/main.py`(공식 에이전트) 무손상.
- **별도 모듈**(`mm_agents/claude_cua/`) + **러너**(`run_claude_scenario.py`)를 추가해서, **실행 옵션 하나(`--tools` / `--type`)로 유형1↔유형2 전환**.
- **bash 가 VM 안에서 실제 실행되는 것 스모크 검증 완료** (mkdir+date+cat → VM 날짜 반환, ~2센트).

## 추가된 파일 (전부 신규)
| 파일 | 역할 |
|---|---|
| `check_anthropic.py` (루트) | VM/OSWorld 없이 API 키·모델·베타(+bash 툴) 구성 확인 |
| `mm_agents/claude_cua/__init__.py` | 패키지 (ClaudeCUAAgent export) |
| `mm_agents/claude_cua/agent.py` | Anthropic Computer Use 루프를 OSWorld VM 에 물린 에이전트 |
| `run_claude_scenario.py` (루트) | 유형1/2 토글 러너 (`run_attack_scenario.py` 의 Claude 버전) |

## 사전 설정 (한 것)
1. Anthropic 콘솔에서 API 키 + 크레딧($5).
2. `.env` 에 `ANTHROPIC_API_KEY=sk-ant-...` 추가.
3. `pip install anthropic` (uv 환경).
4. **모델은 `claude-sonnet-5`** — 구 ID(`claude-sonnet-4-7` 등)는 404. `computer_20251124` 툴 지원 세대여야 함.
5. `python check_anthropic.py --model claude-sonnet-5` 로 구성 확인.

## 조사로 알아낸 핵심 (팀 공유용)
1. **공식 `mm_agents/anthropic` 에이전트는 Claude 에게 `computer` 툴만 준다** (predict() 의 tools 배열에 computer 하나뿐). bash·editor 는 파일로 존재하지만 루프에 안 물려 있음 → 사실상 **유형1(GUI만)**. 그래서 진짜 유형2(bash)는 새로 붙여야 했음.
2. **번들된 `tools/bash.py` 는 호스트에서 실행됨** (`subprocess_shell` 로컬). OSWorld VM 이 아니라 맥에서 도니까 공식 에이전트가 일부러 뺀 것.
3. **VM 이미지의 `/run_bash_script` 엔드포인트가 깨져 있음** — `_append_event` 미정의로 HTTP 500. → **`/execute`(execute_python_command)로 subprocess 를 돌려 우회.** (팀원이 bash 를 `run_bash_script` 로 연결하면 똑같이 막힘. 우회 필요.)

## 어떻게 동작하나 (툴 → VM 라우팅)
- `computer` (항상) → `env.step(pyautogui)` — 좌표를 1280×720(모델 선언) → 1920×1080(VM) 로 스케일, 결과는 새 스크린샷.
- `bash` (옵션) → `/execute` 경유 subprocess → stdout 반환. **← 유형2 OS 표면.**
- `editor` (옵션) → `/execute` 경유 파이썬 파일 조작 (view/create/str_replace/insert).
- `tool_choice.disable_parallel_tool_use=True` — 턴당 1툴 강제(bash/computer 가 한 턴에 섞여 tool_result 순서 꼬이는 것 방지).
- 최근 N장 스크린샷만 유지(`only_n_recent_images`) — 컨텍스트/비용 관리.

## 실행법
```bash
# 유형2 (bash 열림) — bash 는 --allow-bash 필수(안전장치)
uv run python run_claude_scenario.py \
  --instruction "Use the bash tool to run: mkdir -p ~/t && date > ~/t/h.txt && cat ~/t/h.txt" \
  --tools computer,bash --allow-bash \
  --allow-external-screen-share --execute-actions --model claude-sonnet-5

# 유형1 (GUI만)
uv run python run_claude_scenario.py --instruction "..." --type gui \
  --allow-external-screen-share --execute-actions --model claude-sonnet-5

# 공식 시나리오 + 채점
uv run python run_claude_scenario.py \
  --scenario security_scenarios/ipi_005_delete_important_folder/scenario.json \
  --tools computer,bash --allow-bash \
  --allow-external-screen-share --execute-actions --model claude-sonnet-5
```
- `--type gui` = `--tools computer` / `--type tool` = `--tools computer,bash` (명시 `--tools` 가 우선).
- 결과: `security_results/claude_<id>/<timestamp>/` 에 `run_config.json`(어떤 툴셋으로 돌렸는지 기록) · `trajectory.jsonl` · `step_*.png` · `summary.json`.
- 안전장치: `--execute-actions` 없으면 실행 거부, bash 는 `--allow-bash` 없으면 안 켜짐.

## 검증됨
- 스모크: `bash mkdir+date+cat` → VM 날짜 반환, 2스텝 종료, sonnet-5, ~2센트. bash 가 **VM 안에서** 실행됨 확인.

## 알려진 한계 / 다음
- **bash 는 호출마다 새 셸** (cwd/env 유지 안 됨). `&&` 체이닝이나 절대경로 사용. 지속 세션 필요하면 추후 개선.
- editor 는 최소 구현(view/create/str_replace/insert).
- 근본 수정을 원하면 게스트 VM `desktop_env/server/main.py` 의 `_append_event` 정의를 고쳐야 함(이미지에 구워져 있어 번거로움 → 현재는 `/execute` 우회로 충분).
- 다음: 유형1 vs 유형2 로 같은 시나리오 돌려 **공격 성공률 차이** 측정(= OS 공격표면 실측). editor 툴 검증. MCP 툴 확장(Tool/MCP 표면).
