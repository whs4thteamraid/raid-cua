# run_cua 실행기 — 팀 레퍼런스 (옵션 전체 + 통합 변경 + 마이그레이션)

*프로젝트: CUA 공격 표면 분석 및 Red Teaming*
*용도: 통합 실행기(`redteam/run_cua.py`)를 git pull 하는 팀원용. 옛 `run_claude_3` 러너에서 뭐가 바뀌고, 뭘 해야 하는지.*
*정식 문서: `OSWorld/redteam/README_run_cua.md`(CLI 상세) · `README_memory_tool.md`(메모리). 이 문서는 그 위에 "변경·주의"만 얹은 것.*

---

## 0. TL;DR — pull 하면 당장 할 것

1. **진행 중 실험은 통합본에 섞지 마라.** 옛 커밋에서 끝내거나 run_cua로 완전 재기준화. (반쯤 마이그레이션 = 에러 안 나는데 데이터 오염)
2. **호출부 2개 고치기**: `run_claude_3` → `run_cua`, `--allow-bash` 제거(→ `--tools computer,bash`).
3. **결과 비교는 재기준화 후**: temperature 등 기본값이 바뀌어서 통합 전 숫자랑 직접 비교 불가.

---

## 1. 통합 변경사항 (run_claude_3 → run_cua)

### A. 확실히 에러 나는 것

| 깨지는 것 | 이유 | 조치 |
|---|---|---|
| `python -m redteam.run_claude_3` / `import run_claude_3` | 파일이 `run_cua`로 rename → 모듈 없음 | 이름만 `run_cua` |
| `--allow-bash` | 제거됨 | `--tools computer,bash` 로 |

모듈 레벨 함수(`load_scenario`·`resolve_tools`·`main` 등)와 나머지 CLI 플래그는 이름 그대로 → import 경로/명령 이름만 바꾸면 파싱은 됨.

### B. 안 터지는데 조용히 달라지는 것 (진짜 주의)

정렬 상수가 코드에 박혀 있음(`mm_agents/adapters/agents.py`):

| 항목 | 옛 haiku 러너 | run_cua | 상수 |
|---|---|---|---|
| temperature | 미전송 = 1.0 | **0.6** | `TEMPERATURE=0.6` |
| max_tokens | 제각각 | **6000** | `MAX_TOKENS=6000` |
| only_n(최근 이미지 수) | 없음 | **6** (`--only-n`, 0=무제한) | — |
| Kimi top_p | — | **0.95 고정** | `KIMI_TOP_P=0.95` |
| Luna reasoning | — | **`none` 명시** | `REASONING_EFFORT="none"` |
| Kimi 확장추론 | — | payload에 `thinking={"type":"disabled"}` 주입해야 실제 OFF | — |

→ **통합 전/후 결과 직접 비교 금지.** baseline 새로.

---

## 2. run_cua 전체 옵션 (실측)

### 실행 소스 (택1, 필수)
| 옵션 | 뜻 |
|---|---|
| `--scenario <json>` | OSWorld/보안 시나리오 JSON |
| `--instruction "<text>"` | 자유 문구(스모크용) |

### 모델·도구
| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--model` | `claude-haiku-4-5` | `haiku` \| `luna` \| `kimi` 또는 정식 모델 ID |
| `--tools` | (없음) | `computer[,bash][,editor][,mcp]` — `--type`보다 우선 |
| `--type` | `gui` | 레거시: `gui`=computer, `tool`=computer,bash (명시 `--tools`가 이김) |

### VM·실행
| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--path-to-vm` | None | vmx 경로 |
| `--snapshot` | `init_state` | 시작 스냅샷 |
| `--max-steps` | None | 최대 스텝(시나리오 기본값 사용 시 생략) |
| `--pause` | 1.0 | 행동 후 대기(초) |
| `--initial-wait` | 3.0 | 첫 화면 전 대기 |
| `--send-width` | 1280 | 모델에 보내는 이미지 폭 |
| `--only-n` | 6 | 문맥 유지 스크린샷 수(0=무제한) ★신규 |

### 메모리
| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--memory` | off | 지정 시에만 Memory 도구 활성 |
| `--memstore-dir` | None | 호스트 memstore 경로 (§5 — CLI는 준 경로 그대로) |
| `--read-mode` | `faithful` | `faithful`\|`neutral`\|`controlled`\|`inject` |

### 시스템 프롬프트·승인·MCP
| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--system-prompt` / `--system-prompt-file` | None | 인라인 / UTF-8 파일 (택1) |
| `--system-prompt-mode` | `append` | `append`\|`replace` |
| `--approval-mode` | `off` | `interactive` = `request_user_approval` 노출 + 호스트 stdin y/N |
| `--mcp-config` | None | MCP 설정 JSON (`--tools`에 `mcp` 필요) |

### 실행 동의 (둘 다 있어야 실제 Agent 실행)
`--allow-external-screen-share` · `--execute-actions` — 하나라도 없으면 모델 실행 전 중단.

### 보조 모드 (상호배타 — VM/모델 실행 전에 확인만)
| 옵션 | 어디까지 |
|---|---|
| `--config-check-only` | 옵션 해석만. VM·모델·evaluator 미실행 |
| `--setup-only` | VM + 시나리오 setup까지. 모델 미실행 |
| `--mcp-check-only` | VM setup + MCP 탐색까지. 모델·evaluator 미실행 |

### 팝업 주입 실험
`--inject-popup` · `--popup-pos {center,bottom,top}` · `--popup-no-ad` · `--popup-xy`

---

## 3. 모델별 도구 지원 (중요 — Luna/Kimi는 다름)

`validate_request`가 VM 띄우기 **전에** 판정. 지원 안 하는 조합은 조용히 다른 조건으로 도는 대신 거부됨.

| 모델 | native | 에뮬(emulated) | 불가 |
|---|---|---|---|
| Claude(haiku) | computer·bash·editor·mcp·memory·approval·popup | — | — |
| Luna / Kimi | computer | bash·memory·approval | **mcp·editor** (거부) |

→ Luna·Kimi로 `--tools ...,mcp` 나 `editor` 주면 실행 전 에러. 파일 작업은 bash로.

---

## 4. 반복 실행 — run_cua_batch

같은 시나리오를 N회 돌리고 집계. 옵션은 run_cua와 대부분 동일 + 아래.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--scenario` | (필수) | |
| `-n` / `--runs` | 5 | 반복 횟수 |
| `--between-runs` | 2.0 | 실행 사이 대기(초) |

주의:
- batch 요청 자체가 반복 실행 동의로 처리 → 자식 러너에 `--allow-external-screen-share`·`--execute-actions` 자동 전달.
- batch는 `condition=attack` 시나리오만 받음. control 팔은 따로 실행(ASR 집계 분리).
- 집계: `batch_results/.../batch_summary.json` + `runs.csv`. 개별 원본은 `security_results/`(gitignore).

---

## 5. memstore 경로 규칙 (README에 아직 없음 — 코드 docstring에만)

- **CLI `--memstore-dir`** → 준 경로를 **그대로** 씀. 모델분리 안 함.
- **시나리오 스크립트(`run_chain` 등)가 `memstore_for(model, base)`를 쓰면** → `<base>_<모델키>`로 **모델별 분리**. 예: `redteam/memstore_haiku` · `_kimi` · `_luna`.
- 이유: 세 모델이 한 폴더 공유 시 정리 한 번 실패로 노트가 다음 판에 섞이는 사고 방지.
- **시행마다 비우는 것은 그대로.** 모델이 보는 경로는 셋 다 가상 루트 `/memories`라 조건 차이 없음.

---

## 6. 마이그레이션 체크리스트 (pull 후 순서)

1. **진행 중 실험 있으면** → 안 섞기. 옛 커밋에서 마무리 or run_cua로 재기준화.
2. **호출부** → `run_claude_3`→`run_cua`, `--allow-bash` 제거.
3. **`README_run_cua.md`** 새 사용법 훑기(승인 모드·`--tools` 등).
4. **실제 판 전에** `--config-check-only`로 도구·옵션 활성 상태 확인 → 스모크 → 실행.
5. **결과 비교 필요하면** §1-B 상수 인지하고 baseline 새로.
6. 의존성 파일(requirements·pyproject·uv.lock)은 **안 바뀜** → env 재설치 불필요.

---

## 7. summary.json 바뀐 점 (파서 쓰는 사람)

- `conditions` 지문 추가(런타임 실제 조건: temperature·thinking·memory_arm·measured 등) — 페이즈별로 따로.
- `tools_enabled`가 이름 목록이 아니라 `{도구: native|emulated}` dict.
- 도구 문법오류 수(`tool_syntax_errors`) 기록 — 0이 아니면 그 시행은 의심 대상.
