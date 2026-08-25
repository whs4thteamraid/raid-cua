# raid-cua — CUA 레드팀 하네스 (팀 공용)

OSWorld 위에서 **Claude Computer Use Agent(CUA)**를 레드팀하는 팀 공용 저장소.
에이전트 로직은 **OS 무관 단일 코드**(Mac·Windows 동일)이고, 메모리 기능은
Anthropic **공식 memory tool(`memory_20250818`)** 위에 얹혀 있다.

---

## 🚀 빠른 시작 (새로 clone 한 사람)

```bash
git clone https://github.com/whs4thteamraid/raid-cua.git
cd raid-cua/OSWorld

uv sync                                                # 의존성 설치 (anthropic==0.84.0 핀)
# .env 에 ANTHROPIC_API_KEY 넣기 (커밋 금지)

uv run python mm_agents/claude_cua/memory_backend.py   # 백엔드 자체검증 → 14/14 PASS
uv run python redteam/smoke_memory.py                  # 공존·3팔 동작 확인
```

- **Mac**: VMware Fusion + 스냅샷 → `platform-setup/mac/README.md`
- **Windows**: VMware Workstation + 스냅샷 → `platform-setup/windows/README.md`

---

## 📁 디렉토리 구조 (루트)

```
raid-cua/
├── OSWorld/            # ★ 코드 본체 + 런타임 산출물 (아래 참고)   [코드=git 추적 / 런타임=미추적]
├── docs/               # 팀 문서 (환경구축·실험설계·시나리오제작)   [git 추적]
├── platform-setup/     # OS별 환경 셋업 안내 (mac / windows)       [git 추적]
└── README.md
```

**`OSWorld/` 안의 런타임/대용량 폴더** (전부 `.gitignore`로 **미추적**):

```
OSWorld/
├── (코드: desktop_env/ · mm_agents/ · redteam/ · evaluation_examples/ · run.py …)  [git 추적]
├── vmware_vm_data/     # VM 이미지·스냅샷 (Ubuntu0/Ubuntu0.vmx)
├── security_results/   # 실험 결과
└── results/  logs/  cache/  _handoff/   # 런타임 산출물
```

> ⚠️ **이 런타임 폴더들은 반드시 `OSWorld/` 밑에 있어야 한다.** 러너가 `desktop_env/`와
> **같은 층**에서 VM·결과 경로를 찾기 때문(`PROJECT_DIR = desktop_env/ 있는 상위`).
> 루트에 두면 러너가 VM을 못 찾는다.
>
> **[미추적]** = `.gitignore`로 커밋에서 빠짐. clone 하면 안 생기고, 각자 환경에서 실행하며
> 로컬에 쌓이는 것들(용량·비밀·개인 산출물). **정상이다.**

---

## 🔀 기존 팀원 이전 가이드 (옛 레이아웃 → raid-cua)

예전엔 모든 게 저장소 **루트에 평평하게** 있었는데, 이제 **코드가 전부 `OSWorld/` 밑으로**
내려갔고 git 히스토리도 **새로 시작**(업스트림 끊음, remote = `whs4thteamraid/raid-cua`)했다.
→ **기존 체크아웃에 `git pull` 하지 말 것** (히스토리가 무관해서 안 됨). **새로 clone** 한다.

### 1) 새로 clone

```bash
git clone https://github.com/whs4thteamraid/raid-cua.git
```

### 2) 옛 체크아웃에서 "로컬 전용" 파일만 새 위치로 복사

> **코드는 clone에 이미 다 들어있다 — 손으로 옮기지 마.** (`desktop_env/`·`mm_agents/`·
> 공용 `redteam/`(`run_claude_scenario.py`·`smoke_memory.py` 등)·`evaluation_examples/`·`run.py`·
> `monitor/.env` 는 git이 관리 → clone하면 `OSWorld/` 밑에 자동.)
> 네가 옮길 건 **git에 안 올라가는(gitignore) 개인·런타임 파일**뿐 — 아래가 그 전부다:

| 실제로 무엇 | 옛 위치 | 새 위치 |
|---|---|---|
| **개인 시나리오 — 폴더째로** (각 `ipi_XXX_*/`. 안의 `scenario.json`·`serve.py`·`webroot/`(html)·`phase2_*.json`·`exfil_*.jsonl`·README 전부 딸려옴) | `security_scenarios/ipi_XXX_*/` | `OSWorld/security_scenarios/ipi_XXX_*/` |
| **메인 `.env`** (ANTHROPIC_API_KEY) | `.env` | `OSWorld/.env` |
| **VM 이미지·스냅샷** | `vmware_vm_data/` | `OSWorld/vmware_vm_data/` |
| **옛 실험 결과** (보관하려면) | `security_results/` | `OSWorld/security_results/` |
| **메모리 산출물** (있으면) | `redteam/memstore/` | `OSWorld/redteam/memstore/` |
| **개인 러너** (자기 것, gitignore된 것) | `redteam/run_memory_scenario.py`·`set_host_ip.sh` | `OSWorld/redteam/` |

> **시나리오는 폴더 통째로** 옮기면 안에 뭐가 있든(html·서버·이미지·json·로그) 다 따라온다.
> clone 하면 `security_scenarios/`는 골격(README·.gitkeep)만 있고 **비어있다** — 각자 자기 폴더를 넣는다.
> `.venv/`·`_handoff/`·`cache/`·`logs/`·`results/`는 **안 옮김** (`.venv`는 아래 `uv sync`로 새로,
> 나머지는 스크래치라 실행하면 `OSWorld/` 밑에 새로 생김).

### 3) 파일 이동만으로 안 되는 2단계 (필수)

파일을 제자리에 뒀어도 아래 둘을 안 하면 안 돈다.

| # | 해야 함 | 왜 |
|---|---------|-----|
| ① | `cd raid-cua/OSWorld && uv sync` | `.venv/`는 옮기는 게 아니라 **새로 만드는 것.** 없으면 실행 자체가 안 됨 |
| ② | VMware에서 옮긴 `.vmx` **재등록** (Fusion 메뉴 **File→Open→**`OSWorld/vmware_vm_data/Ubuntu0/Ubuntu0.vmx` → **"I Moved It"**) | `vmware_vm_data/` 폴더를 옮겨도 **VMware는 옛 경로를 기억** → "File not found" |

### 4) 조건부 (해당될 때만)

- **`.env`의 API 키가 유효**해야 함 (파일만 있고 키 만료면 실패).
- **host 서버(`serve.py`) 쓰는 시나리오**를 돌릴 거면 → `bash redteam/set_host_ip.sh` 한 번.
  복사해온 시나리오엔 옛 IP가 박혀 있어서, 자기 네트워크 IP로 갱신해야 VM이 호스트를 찾는다.
- 구글 태스크(OSWorld 원본) 돌릴 거면 `evaluation_examples/settings/google*` 크리덴셜 별도 배치.
  (우리 Claude CUA 레드팀 경로엔 **불필요**.)

### 5) 확인

```bash
cd raid-cua/OSWorld
uv sync
uv run python mm_agents/claude_cua/memory_backend.py            # 백엔드 14/14 PASS
uv run python redteam/smoke_memory.py                           # 메모리 도구 동작(API)
uv run python redteam/run_claude_scenario.py --instruction "noop" --setup-only   # VM 부팅 확인
```

세 개 다 통과하면 이전 완료.

---

## ⭐ 우리가 만든 핵심 (팀이 실제로 건드리는 곳)

### `OSWorld/mm_agents/claude_cua/` — 에이전트 (OS 무관 단일 코드)

| 파일 | 역할 | 건드림? |
|------|------|---------|
| `agent.py` | Claude CUA 기본 에이전트. computer/bash/editor 도구 루프. **OS 통합본**(Win·Mac 공용) | 원칙상 X |
| `agent_memory.py` | 위를 상속해 **공식 memory 도구**를 물린 서브클래스. read_mode 3팔(faithful/controlled/inject) | 확장만 |
| `memory_backend.py` | 공식 memory 도구의 **저장 백엔드**(`/memories` → 호스트 폴더). seed/clear/path-traversal 방어 | 원칙상 X |
| `popup.py` | 시각적 프롬프트 인젝션 팝업 렌더러 (스크린샷 합성). `agent.py`와 **세트** | 원칙상 X |
| `README.md` | 에이전트 상세 설명 | — |

> 에이전트는 OS를 직접 안 건드린다. 클릭·타이핑·파일은 전부 **OSWorld controller(`env`)**를
> 통해 VM 안에서 일어나므로, 호스트가 Mac이든 Windows든 **같은 코드가 그대로 돈다.**
> OS가 갈리는 건 `pyproject.toml`의 platform-marker 의존성(pyobjc/pywin32)과
> `platform-setup/`의 셋업 문서뿐 — **코드 분기 아님.**

### `OSWorld/redteam/` — 러너 & 검증 (공용)

| 파일 | 역할 |
|------|------|
| `smoke_memory.py` | 메모리 도구 공존·auto-view·3팔 **환경 검증**(30초) |
| `README_memory_tool.md` | 메모리 이관 모듈 팀 공유 설명서 |
| `check_anthropic.py` | SDK/키 점검 |
| `set_endpoint.py` | 엔드포인트 설정 |

> 각자 **개인 러너·`memstore/`**는 `.gitignore`로 미추적 — 로컬에만 두고 커밋되지 않는다.
> (즉 clone 하면 위 공용 파일만 받고, 개인 실행기는 각자 만들어 쓴다.)

### `OSWorld/security_scenarios/` — 각자 시나리오

- **시나리오는 각자 작성** → 이 폴더에 넣음. `.gitignore`가 하위 폴더를 제외하므로
  **개인 시나리오는 커밋되지 않고**, 골격(`.gitkeep`·`README.md`)만 추적한다.
- 시나리오 하나 = 폴더 하나 (`scenario.json` + 선택 `serve.py`).

### `OSWorld/` 나머지

`desktop_env/`, `evaluation_examples/`, `mm_agents/`(다른 에이전트들), `run.py`,
`batch_run.py`, `monitor/`, `tests/` 등은 **업스트림 OSWorld 벤치 기반**.
우리 작업은 위 세 곳(`claude_cua` · `redteam` · `security_scenarios`)에 집중.

### `docs/` · `platform-setup/`

- `docs/환경구축` · `docs/실험설계` · `docs/시나리오제작` — 팀 문서 자리(채워나감).
- `platform-setup/mac` · `windows` — OS별 셋업 절차.

---

## 🧠 메모리 도구 (read_mode 3팔)

모델이 보는 인터페이스는 **공식 표준 `memory_20250818`**, 저장 백엔드만 우리가 구현.
`/memories`를 **호스트 폴더**에 매핑 → VM 리셋·크리덴셜 로테이션을 넘어 **생존**.

| 팔 | 동작 | 모델링 대상 |
|----|------|-------------|
| `faithful` | 공식 auto-view 유지 → 세션 시작 시 스스로 조회 | 실제 제품(자동 조회) |
| `controlled` | auto-view 억제, 태스크가 요구할 때만 재량 조회 | 신중한 pull 메모리 |
| `inject` | 노트를 첫 메시지에 선주입(조회 불필요) | 항상-컨텍스트 메모리 |

자세한 사용법·설계 원칙 → **`OSWorld/redteam/README_memory_tool.md`**

```python
from mm_agents.claude_cua.agent_memory import MemoryClaudeCUAAgent
from mm_agents.claude_cua.memory_backend import HostMemstoreTool

store = HostMemstoreTool("redteam/memstore")   # 호스트 폴더 = VM 밖
store.clear(); store.seed("note.md", "…노트…")  # 결정론적 초기화(선택)

agent = MemoryClaudeCUAAgent(env, model="claude-haiku-4-5",
                             tools=("computer","bash"),
                             memstore_dir="redteam/memstore",
                             read_mode="faithful")           # faithful|controlled|inject
result = agent.run(instruction, max_steps=18)
# result["memory_views"] / ["memory_writes"] / ["read_mode"] 로 계측
```

---

## ⚠️ 커밋 금지 / 공유 금지

- **`.env`** — `ANTHROPIC_API_KEY` 포함. **절대 커밋 금지** (`.gitignore` 등록됨).
- `redteam/memstore/` — 메모리 실행 산출물 (로컬).
- 각자 개인 러너·개인 시나리오 — 로컬 유지, 미추적.
- Google/GoogleDrive 크리덴셜(`evaluation_examples/settings/...`).

---

## 🔧 의존성 메모

- `anthropic==0.84.0` 핀 (memory tool = Claude 4+; 상속 클래스는 이 버전 `anthropic.lib.tools`).
- `requires-python = ">=3.12,<3.13"` (3.13 상한 — 일부 핀 빌드 이슈 회피).
- `torch` 명시 핀 제거(OpenCUA 전용). 단 `easyocr`/`accelerate`가 전이로 끌어옴 —
  실제 설치엔 남지만 Claude CUA 경로엔 미사용.
- `agp-client`(surferH 로컬 소스) 제거 — Windows에서 `uv sync` 깨지던 원인.
- 팀 전원 **`uv sync`**로 동일 환경. 실제 강제는 `uv.lock`이 한다.
