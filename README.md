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

### ✅ 이렇게 나오면 정상

**`uv sync`** — 459개 resolve 후 설치. (torch 계열 커서 첫 설치는 몇 분 걸릴 수 있음)

```
Resolved 459 packages in ...
Installed N packages in ...
```

**`memory_backend.py`** — 14줄 PASS 후 마지막 줄:

```
  [PASS] create
  [PASS] view dir lists file
  ... (총 14개)
  [PASS] clear empties store
모든 자체검증 통과 ✅
```

**`smoke_memory.py`** — TEST 1~5, 아래 값이 기대치 (확률적이라 애매하면 2~3회):

```
  ✓ TEST1 accepted = True        (computer+bash+memory 동시 선언 수락)
  ● TEST2 auto_view  = True       (무관 태스크에도 스스로 memory view)
  ● TEST3 auto_view  = False      (우리 프롬프트로 억제됨)
  ● TEST4 view(benign) = False    (무관 태스크라 조회 안 함)
  ● TEST5 view(cued)   = True     (회상 요구 태스크라 스스로 조회)
```

> 맨 위에 `RequestsDependencyWarning: urllib3 ... doesn't match a supported version!` 가 떠도
> **무해**(무시). `1=True, 3=False, 4=False, 5=True` 면 메모리 이관·3팔 전부 정상.

### 🖥️ OS별 참고 (VM 이미지·앱만 다름, 절차는 위와 동일)

- **Mac (Apple Silicon/ARM)** — VMware **Fusion** + ARM용 Ubuntu 이미지(`Ubuntu-arm`)
- **Windows (x86)** — VMware **Workstation** + x86 Ubuntu 이미지
- VM 위치: `OSWorld/vmware_vm_data/Ubuntu0/Ubuntu0.vmx` · 스냅샷: `init_state` / `github_ready`
- 폴더 이동 후 재등록: `.vmx` **더블클릭 → "I Moved It"** (자세히는 아래 이전 가이드 ②)

---

## 📁 디렉토리 구조 (루트)

```
raid-cua/
├── OSWorld/            # ★ 코드 본체 + 런타임 산출물 (아래 참고)   [코드=git 추적 / 런타임=미추적]
├── docs/               # 팀 문서 (환경구축·실험설계·시나리오제작)   [git 추적]
└── README.md           # ← 셋업·검증·이전 가이드 전부 여기
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
| **자기 시나리오 — 폴더째로** (폴더 이름은 **자유** — 안의 `scenario.json`·`serve.py`·`webroot/`·설정·산출물 전부 딸려옴) | `security_scenarios/<자기 시나리오폴더>/` | `OSWorld/security_scenarios/<자기 시나리오폴더>/` |
| **메인 `.env`** (ANTHROPIC_API_KEY) | `.env` | `OSWorld/.env` |
| **VM 이미지·스냅샷** | `vmware_vm_data/` | `OSWorld/vmware_vm_data/` |
| **옛 실험 결과** (보관하려면) | `security_results/` | `OSWorld/security_results/` |
| **메모리 산출물** (있으면) | `redteam/memstore/` | `OSWorld/redteam/memstore/` |
| **자기 개인 러너·스크립트** (로컬에만 두던 것) | `redteam/<자기 러너>.py` 등 | `OSWorld/redteam/` |

> **폴더 이름은 각자 다르다.** `security_scenarios/` **밑의 모든 하위 폴더가 gitignore**라
> (이름 무관), clone 하면 이 폴더는 골격(README·.gitkeep)만 있고 **비어있다** —
> 자기 시나리오 폴더를 **이름 그대로** 여기에 넣으면 된다. (예: 박규남=`ipi_025_*`, 다른 팀원=자기 명명)
> **폴더 통째로** 옮기면 안에 뭐가 있든(html·서버·이미지·json·로그) 다 따라온다.
> `.venv/`·`_handoff/`·`cache/`·`logs/`·`results/`는 **안 옮김** (`.venv`는 아래 `uv sync`로 새로,
> 나머지는 스크래치라 실행하면 `OSWorld/` 밑에 새로 생김).

### 3) 파일 이동만으로 안 되는 2단계 (필수)

파일을 제자리에 뒀어도 아래 둘을 안 하면 안 돈다.

| # | 해야 함 | 왜 |
|---|---------|-----|
| ① | `cd raid-cua/OSWorld && uv sync` | `.venv/`는 옮기는 게 아니라 **새로 만드는 것.** 없으면 실행 자체가 안 됨 |
| ② | VMware에서 옮긴 `.vmx` **재등록**: `OSWorld/vmware_vm_data/Ubuntu0/Ubuntu0.vmx` 를 **더블클릭해서 실행**(또는 File→Open) → "옮겼냐/복사했냐" 물으면 **"I Moved It"** | `vmware_vm_data/` 폴더를 옮겨도 **VMware는 옛 경로를 기억** → "File not found" |

> ②는 Mac(VMware Fusion)·Windows(VMware Workstation) **공통**: `.vmx` 더블클릭 → **"I Moved It"**.
> ⚠️ `I Copied It` 누르면 UUID·MAC이 새로 생겨 스냅샷·설정이 틀어짐 — 반드시 **Moved**.
> 라이브러리에 남은 **옛 경로 항목**은 지워도 되는데, **파일 삭제 옵션은 피할 것**
> (Fusion=`Keep Files` / Workstation=`Remove from Library` 선택, `Move to Trash`·`Delete from Disk` ✗).

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
> VM 이미지·VMware 앱 종류뿐 — **코드 분기 아님.**

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

### `docs/`

- `docs/환경구축` · `docs/실험설계` · `docs/시나리오제작` — 팀 문서 자리(채워나감).

---

## 🧪 검증 스크립트 (스모크)

환경이 제대로 잡혔는지 **VM 없이** 빠르게 확인하는 두 스크립트. (`cd OSWorld` 에서 실행)

### 1. `memory_backend.py` — 백엔드 자체검증 (로컬, API 키 불필요)

```bash
uv run python mm_agents/claude_cua/memory_backend.py
```

호스트 memstore 백엔드의 6커맨드(view/create/str_replace/insert/delete/rename) + path-traversal
방어 + seed/clear 를 로컬에서 검증. **`모든 자체검증 통과 ✅ (14/14)`** 나오면 OK.
API 호출 없음 → 키·네트워크·VM 전부 불필요.

### 2. `smoke_memory.py` — 메모리 도구 API 스모크 (키 필요, VM 불필요, ~30초)

```bash
uv run python redteam/smoke_memory.py                 # 기본 haiku-4.5
uv run python redteam/smoke_memory.py --model claude-sonnet-5   # 모델 바꿔서
```

`.env` 자동 로드(`ANTHROPIC_API_KEY`). VM(DesktopEnv) 안 띄우고 API 호출 1~2번으로 관측:

| TEST | 확인하는 것 | 기대 |
|------|-------------|------|
| 1 공존 | `computer`+`bash`+`memory_20250818` 동시 선언을 서버가 400 없이 수락? | `accepted=True` |
| 2 auto-view | 무관 태스크에도 모델이 스스로 `memory(view)` 를 첫 행동으로? | `True` (프로토콜 존재) |
| 3 억제 | 우리 system 프롬프트로 auto-view 를 끌 수 있나? | `False` (통제 가능) |
| 4 controlled+benign | 재량 모드 + 무관 태스크 → 조회 안 함? | `view=False` |
| 5 controlled+cued | 재량 모드 + 회상 요구 태스크 → 스스로 조회? | `view=True` |

> 1=accepted, 3=False, 4=False, 5=True 면 **메모리 이관·3팔 전부 정상.**
> (확률적 모델이라 1회는 참고치 — 애매하면 2~3회 재실행.)

두 스크립트 다 통과하면 메모리 쪽은 그린. 실제 VM 조작까지 보려면
`run_claude_scenario.py`로 부팅만(`--setup-only`) → 풀 실행. 이때 아래 안전 플래그가 필요하다.

### ⚠️ 실행 플래그 — 안전 가드 (자주 걸리는 것)

러너를 그냥 돌리면 이렇게 **거부**된다 (버그 아님, 의도된 가드):

```
거부: 화면을 확인한 뒤 --allow-external-screen-share 와 --execute-actions 를 함께 주세요.
```

실제로 액션을 실행하려면 **명시적 동의 플래그**를 켜야 한다:

| 플래그 | 동의하는 내용 | 언제 필요 |
|--------|---------------|-----------|
| `--execute-actions` | 모델의 액션을 VM에서 **실제 실행** | 항상 (실행하려면) |
| `--allow-external-screen-share` | **VM 스크린샷을 Anthropic API로 전송** | 항상 (실행하려면) |
| `--allow-bash` | **셸 명령이 VM에서 실제 실행됨** | `bash` 툴 켤 때(`--type tool` 등) |

```bash
# 부팅만 확인 (가드 안 걸림 — 모델 호출 없음)
uv run python redteam/run_claude_scenario.py --instruction "noop" --setup-only

# 실제 한 바퀴 (bash 포함이면 세 플래그 다)
uv run python redteam/run_claude_scenario.py \
  --instruction "Open a terminal and run: echo hello" \
  --type tool --allow-external-screen-share --execute-actions --allow-bash --max-steps 6
```

> 매번 명시적으로 켜야 실행되게 해둔 안전장치라 **정상**이다. 팀 표준 시나리오 실행에도 늘 붙는다.
> (`--setup-only`는 모델을 안 부르니 이 플래그들 없이도 통과 — VM 부팅 확인용.)

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
