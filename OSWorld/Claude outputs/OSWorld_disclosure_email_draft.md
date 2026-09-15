# 메인테이너 통보 메일 초안

**From:** ksasha@ajou.ac.kr  ← 학교 메일로 발송할 것 (아래 사유)
**To:** yuanmengqi732@gmail.com, tianbaoxiexxx@gmail.com, zzl0712@connect.hku.hk
**Subject:** Private security report — guest-controlled code executed with evaluator privileges (OSWorld 1.0 & 2.0)

### 수신자 출처 (2026-09-07 확인)

세 주소 모두 **저장소 README 가 "current maintainer" 로 명시한 것**이며 추측이 아니다.

| 주소 | 출처 | 비고 |
|---|---|---|
| `yuanmengqi732@gmail.com` | V1 README:252 **및** V2 README:312 | **양쪽 모두에 등재 — 가장 확실** |
| `tianbaoxiexxx@gmail.com` | V1 README:252 | V2 목록에서는 빠짐. OSWorld 논문 제1저자 |
| `zzl0712@connect.hku.hk` | V2 README:312 | V2 에서 추가됨. **기관 도메인(HKU)** |

우리 신고는 **두 저장소 모두**를 다루므로 셋 다 넣는다. V1 만 보고 `tianbaoxiexxx` 에게만 보내면 V2 담당자가 빠지고, V2 만 보면 V1 제1저자가 빠진다.

**주의 — 이 주소들은 보안용으로 지정된 것이 아니다.** README 원문 맥락은 *"리더보드 검증 결과를 등재하려면 미팅을 잡아라"* 이다. 즉 **보안 신고를 상시 감시하는 주소가 아닐 수 있다.** 이것이 (a) Discord 수신 확인 절차와 (b) 리마인더 일정이 형식이 아니라 실질인 이유다.


---

Dear OSWorld maintainers,

My name is PARK Gyu-nam. I am a trainee on Team RAID at WhiteHat School (4th cohort), a security training programme operated by KISA, the Korea Internet & Security Agency. Our project is an attack-surface analysis of computer-use agents. I am writing in a personal research capacity — this is not an official communication from KISA — to report a security issue in OSWorld privately, before any public discussion.

**In short:** the official evaluation path copies Python files that the agent can modify inside the guest VM into the evaluation environment, then executes them (`check_python_file_by_test_suite`). Code whose content is controlled from inside the guest therefore runs with the privileges of the evaluation process. In the documented default deployment that process runs on the host.

**This affects both current releases:**

- `xlang-ai/OSWorld` @ `fc31a90` (= `main`) — `metrics/vscode.py:258`, executed in a child process
- `xlang-ai/OSWorld-V2` @ `1c81bd34` (= `main`) — `metrics/vscode.py:304`, executed **in-process**, with no subprocess boundary

The same two task definitions carry the path in both repositories (`9219480b-…` and `26150609-…`), byte-identical.

I reproduced this on a clean clone of OSWorld 1.0 at `fc31a90` with zero patches, using the unmodified tetris task. No task-config tampering or exploitation primitive was needed — only the file edit the task itself asks the agent to make. The evaluator returned its normal score, so the run left no anomaly in the grading log. For OSWorld 2.0 I verified the identical code path and task configuration by inspection but **did not run it**, and the report says so.

**Where to start: `OSWorld_security_report.pdf`.** It is self-contained and takes about ten minutes; everything else is supporting material it references. If you only read one thing, read §3 (the call flow, with line numbers) and §4 (how to reproduce it). §8A is a self-verification procedure you can run against a fresh clone in a couple of minutes without touching a VM.

The remaining attachments, in the order the report cites them:

- `F2_call_flow_evidence.md` — line-number audit table and the full verification procedure
- `f2_upstream_verify.py` — the reproduction script (§4)
- `classify_tasks.py` — reproduces the impact counts in §2 and §6
- `hf_test.py`, `settings_original.py` — preserved copies of two files the report hashes
- `MANIFEST.txt` — sha256 for all of the above, so you can confirm nothing changed in transit
- `OSWorld_security_report.md` — the report again as plain text, if you want to copy the verification commands

The payload used in the reproduction only writes a canary file — no network activity and no persistence.

Before writing I looked for a private reporting channel: there is no `SECURITY.md` in either repository, and GitHub private vulnerability reporting is not enabled (`/security/advisories/new` is unavailable). That is why I am writing to you directly. If you enable private vulnerability reporting, or prefer another channel, tell me and I will move there immediately — I would rather this be tracked in a place that suits you.

I propose a 90-day coordinated disclosure window and am happy to adjust to whatever suits you.

On the CVE: I intend to request an identifier, and I would rather coordinate with you than act on my own. If you would like to file it yourselves — a GitHub Security Advisory would do it, with GitHub as CNA — please go ahead; I would only ask that the advisory credit me as "PARK Gyu-nam, Team RAID — WhiteHat School (KISA)" and that you add me as a collaborator on the draft so I can check the technical details first. If you would rather not, or if nothing has been filed by day 45, I will request one through MITRE, name you as the vendor, and send you the text for review beforehand. Either way I will not publish before the agreed date or before a fix is available, whichever comes first.

Two things about timing, both mentioned in advance rather than afterwards.

My training programme holds an internal results presentation on **17 October 2026**, day 40 of the proposed window. I am raising it before we agree the window rather than after.

The audience is programme participants and staff and it is not a public event, but I should be straight with you about the limits of that: the session may be recorded for the programme's internal use, and attendees are not under a confidentiality agreement. I will not post slides or materials publicly before the coordinated date.

I would like to present the analysis method, the measured results, and the disclosure process. **Unless you tell me otherwise, I will hold back anything that would let someone reproduce the issue** — payload, reproduction script, step-by-step chain — and present it at a level that does not enable reproduction. If you are comfortable with more, tell me; if you would prefer less, tell me that. Absent a reply I default to the restrictive option.

Separately, I may publish part of this work — the agent-behaviour findings, not the vulnerability mechanics — in an academic paper on computer-use-agent security. That is not decided yet. If it happens, I would share a draft with you beforehand.

If you would like to be acknowledged in anything I publish about this, tell me how you would like to be named.

Thank you for OSWorld — the benchmark has been valuable for our research, and I hope this report is useful.

Best regards,

PARK Gyu-nam (박규남)
Ajou University · Team RAID, WhiteHat School 4th cohort (KISA)
ksasha@ajou.ac.kr  (backup: kevin965546184644@gmail.com)

**Attachments:**
- `OSWorld_security_report.md`
- `F2_call_flow_evidence.md`
- `f2_upstream_verify.py`, `classify_tasks.py`
- `hf_test.py`, `settings_original.py`

---

## 발송 전 체크리스트

- [x] ~~이름 / 소속~~ — PARK Gyu-nam, Team RAID · WhiteHat School 4th (KISA)
- [x] ~~메일 주소~~ — 학교 `ksasha@ajou.ac.kr` 발송·주연락, 개인 지메일 백업 병기
- [ ] 학교 메일에서 **첨부 용량 제한** 확인 (스크립트·문서 합계 수백 KB 수준이라 문제없을 것)
- [ ] **전화번호는 넣지 않는다** — 아래 사유 참조
- [ ] 팀·멘토에게 발송 사실 공유 (크레딧이 아니라 절차 문제)
- [x] ~~HF `settings.py` 해시 대조~~ — 2026-09-07 완료, `fca04a7c…` 일치 확인
- [x] ~~OSWorld 2.0 영향 여부~~ — 확인 완료. 같은 함수·같은 태스크·**서브프로세스 없이 in-process 실행**
- [ ] V2 동적 재현을 할지 결정 — 안 해도 신고는 가능(정적 근거 명시). 하면 주장이 더 강해지나 VM 환경 재구축 필요
- [ ] 첨부 파일 5개가 실제로 첨부됐는지 확인
- [ ] Annex B(에이전트 행동 실험)를 첨부할지 결정 — **1차 통보에는 빼는 쪽을 권함.** 본문 주장과 무관하고, 메인테이너가 그쪽을 먼저 물고 늘어질 수 있다. 요청받으면 그때 보내면 된다.
- [ ] 시나리오 JSON·페이로드 파일은 **첨부하지 않는다** (재현에는 불필요하고, 완성된 공격 문서를 배포하는 셈이 된다)
- [ ] 발송 시각 기록 → 90일 카운트 시작점
- [ ] 회신 없을 경우 대비: 14일 후 리마인더, 30일 후 2차 리마인더, 그래도 무응답이면 MITRE 직접 신청 검토

## 10/17 내부 발표 — 실제 제약

발표일이 D+40, 90일 창 한가운데다. **90일을 요청해놓고 40일차에 작동하는 재현 자료를 공개하면 조율 공개 위반이다.** 청중이 보안 교육생이어도 NDA 가 없고, 녹화될 수 있고, 수십 명이며, 자료는 돌아다닌다.

그래서 신고서 문구를 **약속이 아니라 요청**으로 바꿨다. 못 지킬 약속을 적는 것이 안 적는 것보다 나쁘기 때문이다. 녹화 가능성과 비밀유지 부재도 솔직히 적었다.

### 기본값 (회신이 없거나 "제한해달라"는 경우)

**슬라이드에 넣지 않는다**

- 페이로드 코드 (`pathlib.Path('/tmp/...').write_text(...)` 등)
- 재현 스크립트, 시나리오 JSON, 오염 README 전문
- `sys.path.insert` → `exec_module` 로 이어지는 단계별 체인
- `vscode.py:287` 수준의 파일·행 세부

**넣어도 되는 것 — 발표의 실질은 여기 다 있다**

- 발견 경위와 검증 방법론 (해시 대조, 업스트림 무패치 재현, 적대적 리뷰 5라운드 대응)
- CVSS 8.5 (High), 영향 범위 2/369, OSWorld 2.0 도 동일
- **C-1 실험 전체** — 거부 0/17, A≈C, 판단 축 무력화. 이건 재현 정보가 아니다
- 책임공개 절차와 일정

*"재현 코드는 조율 공개일 전이라 제외했습니다"* 슬라이드 한 장이 오히려 전문가답게 읽힌다.

### 메인테이너가 "더 상세해도 좋다"고 답한 경우

그 회신을 **반드시 보관**하고, 슬라이드 각주에 근거를 남긴다.
> Technical detail included with the maintainers' written consent, [날짜].

### 발표 후 — 실제로 제일 흔한 사고 경로

- **슬라이드를 velog·GitHub·LinkedIn 등에 올리지 않는다.** 조율된 공개일(2026-12-06) 전까지.
- 팀원·멘토에게도 같은 제약을 명확히 전달한다. 내가 안 올려도 남이 올리면 결과는 같다.
- 녹화본이 프로그램 외부로 나가지 않는지 운영진에게 확인해둔다.

### 발표에 세부를 꼭 넣어야 한다면

D+30(10/07) 2차 리마인더 때 **명시적으로 다시 물어라.** 발표 열흘 전이라 회신 여유가 있다. 그때도 무응답이면 제한 방침으로 간다.

## CVE 크레딧 확보에 관한 주

메인테이너가 GitHub Security Advisory 를 올리면 **GitHub 이 CNA 로 CVE 를 발급**하고, 그 advisory 의 Credits 섹션은 **메인테이너가 채운다.** 악의가 아니라 그냥 누락되는 일이 흔하고, 한 번 발급되면 크레딧 수정은 훨씬 번거롭다.

그래서 보고서와 메일에 세 가지를 못박았다.

1. **크레딧 문구를 우리가 먼저 제시** — `PARK Gyu-nam, Team RAID — WhiteHat School (KISA)`. 상대가 알아서 적어주기를 기다리지 않는다.
2. **초안 advisory 의 collaborator 로 추가 요청** — GitHub 은 신고자를 draft advisory 에 참여시킬 수 있다. 게시 전에 크레딧과 기술 세부를 직접 확인할 수 있다.
3. **45일차 자체 신청 기한 명시** — 그때까지 신청이 없으면 우리가 MITRE 에 직접 낸다고 미리 적었다. **보고서에 써 뒀으므로 그날 통보 없이 진행해도 결례가 아니다.**

이 셋이 없으면 "우리가 알아서 할게요" 한마디에 주도권이 넘어가고, 몇 달 뒤 크레딧 없는 CVE 를 보게 될 수 있다. 요청 톤은 정중하되 기한과 문구는 명시하는 것이 표준이다.

**발송 메일은 반드시 보관할 것.** 타임스탬프가 최초 신고 사실의 증거다. 분쟁이 생기면 그게 유일한 근거다.

## 연락처·소속 표기에 대한 주

**발신은 학교 메일(`ksasha@ajou.ac.kr`)로.** 받는 쪽은 홍콩대 연구자들이다. `.ac.kr` 기관 도메인은 검증 가능한 소속을 즉시 드러내고, 학계 간 통신 관례에도 맞는다. 반면 `kevin965546184644@gmail.com` 은 숫자가 길게 붙은 주소라 처음 받는 사람에게는 자동생성 계정이나 일회용처럼 보일 수 있다. 보안 신고에서 첫인상은 스팸함 행이냐 아니냐를 가른다.

**단 백업 주소를 함께 적는다.** 90일 창 안에 졸업·계정 만료·학교 메일서버 필터링이 일어나면 스레드가 끊긴다. 서명에 개인 메일을 백업으로 병기하면 그 위험이 사라진다. 이건 과한 조치가 아니라 표준이다.



**전화번호를 넣지 않는 이유.** 이 문서는 해외 메인테이너에게 전달되고, 전달·인용되며, 공개 시점에 CVE 레코드나 어드바이저리에 첨부될 수 있다. **개인 휴대번호가 공개 기록에 들어가면 회수가 불가능하다.** 스팸·사칭·괴롭힘의 입구가 되고, 되돌릴 방법이 없다. 보안 신고의 표준 연락 수단은 메일이며, 상대가 급히 연락할 이유도 없다. 메인테이너가 통화를 원하면 그때 개별로 주면 된다.

**KISA 표기를 조심한 이유.** 화이트햇 스쿨은 KISA가 운영하는 교육 프로그램이고 본인은 그 교육생이다. 그런데 신고서에 `KISA` 만 크게 적으면 받는 쪽이 **국가기관의 공식 통보**로 읽을 수 있다. 그렇게 읽힌 뒤 아니라는 게 드러나면 신뢰가 크게 상한다. 그래서 다음 두 가지를 명시했다.

- `a security training programme operated by KISA` — 프로그램 운영 주체로만 표기
- `This report is submitted in a personal research capacity as a programme trainee. It is not an official communication from KISA.`

이건 소속을 깎아내리는 게 아니라 **정확하게 적어 신뢰를 지키는 것**이다. KISA 프로그램 소속이라는 사실 자체가 이미 신뢰 요소로 작동한다.

## 채널 — 확인 결과

| 채널 | 상태 | 판정 |
|---|---|---|
| `SECURITY.md` / `.github/SECURITY.md` | **없음** (2026-09-07 확인) | 문서화된 신고 절차 없음 |
| GitHub private security advisory | **비활성** — `/security/advisories/new` 폼 안 뜸 (2026-09-07 확인) | 사용 불가 |
| 메인테이너 메일 (README) | 있음 — V1 2개, V2 2개, 중복 1개 → 총 3개 | **유일한 통보 채널** |
| Discord | 있음 | 리마인더 전용 — 아래 참조 |

**메일이 유일한 경로다.** 이 확인 사실 자체를 메일 본문에 적어두면 "왜 개인 메일로 보냈나"는 질문이 사라지고, 우리가 절차를 먼저 찾아봤다는 기록이 된다.

### Discord 사용 규칙

`https://discord.gg/4Gnw7eTEZR` (V1 README 에 링크)

- **공개 채널에 취약점 내용을 절대 쓰지 않는다.** 재현 방법·파일 경로·함수명 어느 것도. 그 순간 비공개 공개(private disclosure)가 아니게 되고, 90일 창도 무의미해지며, 패치 전에 제3자가 알게 된다.
- **DM 도 내용을 담지 않는다.** 다음 정도만:
  > "Hi — I sent a security report to your maintainer email on [날짜] regarding OSWorld's evaluation path. Could you confirm it reached you? Happy to move to whatever channel you prefer."
- 서버에서 **누가 활동 중인 메인테이너인지 파악하는 용도**로는 유용하다. README 의 메일 2개가 죽어 있을 수도 있다.

## 무응답 시 경로

학술 저장소는 보안 메일에 응답이 느리거나 없는 경우가 흔하다. 순서:

1. **D+0** 메일 발송 (메인테이너 2인 To). **발송 시각 기록** — 90일 카운트 시작점이자 나중의 근거.
2. **D+3~5** Discord DM 으로 수신 확인만 요청 (내용 없이)
3. **D+14** 같은 메일 스레드에 짧은 리마인더
4. **D+30** 2차 리마인더. 이때 private advisory 를 켜달라고 다시 요청해볼 것
5. **D+45** 보고서에 명시한 기한. 메인테이너가 CVE 를 신청하지 않았으면 MITRE 에 직접 제출 (https://cveform.mitre.org). 무응답이면 "vendor unresponsive" 로 기재.
   → **이 날짜를 보고서에 미리 못박아 뒀으므로 통보 없이 진행해도 결례가 아니다.** 그게 45일차를 명시한 이유다.
6. **D+90** 합의된 공개일. 패치가 없어도 공개 가능하나, 공개 시점에는 완화책(§7 A~C)을 함께 제시할 것

무응답이라고 해서 공개를 앞당기지 않는다. 기다린 기록 자체가 나중에 우리 쪽 정당성이 된다.
