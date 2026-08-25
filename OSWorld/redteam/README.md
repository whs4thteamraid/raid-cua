# redteam/ — 우리 팀 커스텀 코드 모음

OSWorld-audit(업스트림 프레임워크) 위에 **우리가 추가한 red-team/보안 커스텀 스크립트**만 여기 모아둔다.
프레임워크 자체(`desktop_env/`, `scripts/python/run_multienv_*.py`, `mm_agents/*`)는 건드리지 않는다.

## 여기 있는 파일
| 파일 | 용도 | 두뇌 |
|---|---|---|
| `run_attack_scenario.py` | 단일 공격 시나리오 실행 + 증거 수집 (`security_scenarios/`) | OpenCUA |
| `run_opencua_smoke.py` | OpenCUA↔OSWorld 연결 스모크 | OpenCUA |
| `set_endpoint.py` | RunPod LLM 엔드포인트(.env의 OPENCUA_BASE_URL) 갱신 | OpenCUA |
| `check_anthropic.py` | Anthropic API 키·모델·베타(+bash) 구성 확인 | Claude |

> 이 스크립트들은 **repo 루트를 스스로 찾도록** 고쳐놔서, `redteam/`에 있어도 루트에 있을 때와 똑같이 동작한다.
> 항상 **repo 루트에서 `PYTHONPATH=.` 로 실행**한다 (예: `PYTHONPATH=. uv run python redteam/run_attack_scenario.py ...`).

## 전체 레포 지도 (어디에 뭐가 있나)

**프레임워크(업스트림, 공통 — 안 건드림)**
- `desktop_env/` — DesktopEnv·컨트롤러·evaluator (모든 두뇌 공유)
- `evaluation_examples/` — 태스크셋 · `lib_run_single.py` — 실행 루프 · `vmware_vm_data/` — VM

**두뇌별 에이전트/러너 (프레임워크 관례, 모델마다 하나씩)**
- Claude:  `mm_agents/anthropic/`  +  `scripts/python/run_multienv_claude.py`
- OpenCUA: `mm_agents/opencua/`   +  `scripts/python/run_multienv_opencua.py`
- (그 외 gemini/kimi/gpt… 다수)

**우리 커스텀**
- `redteam/` (이 폴더) · `security_scenarios/` (IPI 시나리오) · `security_results/` (결과)

## 유형1 / 유형2 (Claude)
- **유형1** = `run_multienv_claude.py` (bash 없음, 화면 클릭만)
- **유형2** = `run_multienv_claude.py --enable-bash-tool` (bash 직접 실행)
- `mm_agents/anthropic/main.py`에 bash 버그 3개 수정 반영됨:
  1. `_run_bash_tool`: 깨진 `/run_bash_script` → `/execute`+subprocess 우회
  2. `predict()`: bash 단독 턴 → DONE 대신 WAIT
  3. bash 실행: capture_output → 임시파일 리다이렉트(GUI 실행 60초 블로킹 해결)

## 실행 예 (repo 루트에서)
```bash
# Claude 구성 확인
PYTHONPATH=. uv run python redteam/check_anthropic.py --model claude-sonnet-5

# Claude 유형2 (bash)
PYTHONPATH=. uv run python scripts/python/run_multienv_claude.py \
  --model claude-sonnet-5 --provider_name vmware --path_to_vm "vmware_vm_data/Ubuntu0/Ubuntu0.vmx" \
  --observation_type screenshot --test_all_meta_path evaluation_examples/test_small.json \
  --enable-bash-tool --num_envs 1 --max_steps 12 --result_dir ./results/claude/type2

# OpenCUA 공격 시나리오
PYTHONPATH=. uv run python redteam/run_attack_scenario.py \
  --scenario security_scenarios/ipi_001_visible_web_prompt/scenario.json \
  --allow-external-screen-share --execute-actions
```
