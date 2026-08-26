# redteam/ — 우리 팀 커스텀 코드 모음

OSWorld-audit(업스트림 프레임워크) 위에 **우리가 추가한 red-team/보안 커스텀 스크립트**만 여기 모아둔다.
프레임워크 자체(`desktop_env/`, `scripts/python/run_multienv_*.py`, `mm_agents/*`)는 건드리지 않는다.

## 여기 있는 파일
| 파일 | 용도 | 두뇌 |
|---|---|---|
| `run_claude.py` | **메인 Claude 러너** — 유형1/2 토글, 시나리오 채점, 팝업/해상도 옵션, **메모리 옵션(`--memory`, 기본 off)**. `mm_agents/claude_cua` 커스텀 에이전트 사용 | Claude |
| `smoke_claude_memory.py` | 메모리 도구(memory_20250818) 공존·auto-view·3팔 API 스모크 (VM 불필요, ~30초) | Claude |
| `check_claude_api.py` | Anthropic API 키·모델·베타(+bash) 구성 확인 (preflight) | Claude |
| `README_memory_tool.md` | 메모리 이관 모듈 설명서 | 문서 |
| `run_opencua.py` | 단일 공격 시나리오 실행 + 증거 수집 (`security_scenarios/`) | OpenCUA |
| `smoke_opencua.py` | OpenCUA↔OSWorld 연결 스모크 | OpenCUA |
| `set_opencua_endpoint.py` | RunPod LLM 엔드포인트(.env의 OPENCUA_BASE_URL) 갱신 | OpenCUA |

> **개인(gitignore, clone에 안 들어옴):** `run_claude_memory_2phase.py`(2-phase 메모리 지속성 오케스트레이터) · `set_host_ip.sh`(랩 호스트 IP) · `memstore/`(호스트 메모리 저장).

> 이 스크립트들은 **repo 루트를 스스로 찾도록** 고쳐놔서, `redteam/`에 있어도 루트에 있을 때와 똑같이 동작한다.
> 항상 **repo 루트에서 `PYTHONPATH=.` 로 실행**한다 (예: `PYTHONPATH=. uv run python redteam/run_opencua.py ...`).

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

## Claude 러너 두 갈래 (둘 다 유형1/2 지원)
- **`run_claude.py`** (redteam/, `mm_agents/claude_cua` 커스텀) — `--tools computer`=유형1 / `--tools computer,bash --allow-bash`=유형2. 시나리오 채점·팝업·해상도·**메모리(`--memory`)** 옵션 포함. **우리 IPI/보안 실험 메인.**
- **`run_multienv_claude.py`** (scripts/python/, `mm_agents/anthropic` 공식) — 유형1 / `--enable-bash-tool`=유형2. OSWorld 벤치 멀티환경 배치용.
- 공식 러너 쪽은 `mm_agents/anthropic/main.py`에 bash 버그 3개 수정 반영됨:
  1. `_run_bash_tool`: 깨진 `/run_bash_script` → `/execute`+subprocess 우회
  2. `predict()`: bash 단독 턴 → DONE 대신 WAIT
  3. bash 실행: capture_output → 임시파일 리다이렉트(GUI 실행 60초 블로킹 해결)

## 실행 예 (repo 루트에서)
```bash
# Claude 구성 확인
PYTHONPATH=. uv run python redteam/check_claude_api.py --model claude-sonnet-5

# Claude 커스텀 러너 (유형2 + 메모리 옵션, 기본 off)
PYTHONPATH=. uv run python redteam/run_claude.py \
  --scenario security_scenarios/ipi_001_visible_web_prompt/scenario.json \
  --tools computer,bash --allow-bash --allow-external-screen-share --execute-actions \
  --memory --read-mode faithful --memstore-dir ./memstore

# Claude 공식 벤치 러너 유형2 (bash)
PYTHONPATH=. uv run python scripts/python/run_multienv_claude.py \
  --model claude-sonnet-5 --provider_name vmware --path_to_vm "vmware_vm_data/Ubuntu0/Ubuntu0.vmx" \
  --observation_type screenshot --test_all_meta_path evaluation_examples/test_small.json \
  --enable-bash-tool --num_envs 1 --max_steps 12 --result_dir ./results/claude/type2

# OpenCUA 공격 시나리오
PYTHONPATH=. uv run python redteam/run_opencua.py \
  --scenario security_scenarios/ipi_001_visible_web_prompt/scenario.json \
  --allow-external-screen-share --execute-actions
```
