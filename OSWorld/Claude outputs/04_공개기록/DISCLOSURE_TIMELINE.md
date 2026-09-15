# OSWorld 취약점 책임공개 — 타임라인 기록

> 이 파일은 **CVE 신청 시 "벤더 통보 시점" 증빙**으로 쓰인다.
> 이벤트가 생길 때마다 아래 로그에 추가할 것. 추정·예정은 반드시 그렇게 표시한다.

---

## 사건 요약

| 항목 | 내용 |
|---|---|
| 대상 | `xlang-ai/OSWorld` @ `fc31a90`, `xlang-ai/OSWorld-V2` @ `1c81bd34` (양쪽 모두 `main`) |
| 내용 | 게스트 VM이 통제하는 Python 파일이 평가 프로세스(기본 배포에서 호스트) 권한으로 실행됨 |
| 경로 | `desktop_env/evaluators/metrics/vscode.py` — 1.0 L258 (서브프로세스), 2.0 L304 (인프로세스, 경계 없음) |
| 영향 태스크 | 2개 (`9219480b-…` tetris, `26150609-…` snake), 양 저장소 바이트 동일 |
| CVSS 3.1 | 8.5 (High) |
| 보고자 | PARK Gyu-nam, Team RAID — WhiteHat School 4th cohort (KISA) |
| 신고 채널 | README 명시 메인테이너 3인 직접 메일 (SECURITY.md 없음, GitHub PVR 비활성) |

---

## 로그

### D+0 — 2026-09-07 (월) 11:59 KST / 02:59 UTC — **발송 완료**

- **발신** `ksasha@ajou.ac.kr` (박규남)
- **수신** `yuanmengqi732@gmail.com`, `tianbaoxiexxx@gmail.com`, `zzl0712@connect.hku.hk`
- **제목** `Private security report — guest-controlled code executed with evaluator privileges (OSWorld 1.0 & 2.0)`
- **첨부** 8건 전부 **실제 첨부로 전달 확인** (Drive 링크 대체 없음, Gmail 바이러스 검사 통과)

  | # | 파일 | 확인 |
  |---|---|---|
  | 1 | `OSWorld_security_report.pdf` | ✅ (썸네일 정상 렌더 — 파일 무결) |
  | 2 | `OSWorld_security_report.md` | ✅ |
  | 3 | `F2_call_flow_evidence.md` | ✅ |
  | 4 | `f2_upstream_verify.py` | ✅ |
  | 5 | `classify_tasks.py` | ✅ |
  | 6 | `hf_test.py` | ✅ |
  | 7 | `settings_original.py` | ✅ |
  | 8 | `MANIFEST.txt` | ✅ |

- **증빙**
  - `D+0_발송증빙_20260907_1159KST.png` — 발신·수신·제목·시각
  - `D+0_첨부8건확인_20260907.png` — 첨부 8건 목록 및 서명 블록

발송 본문에서 제안한 내용:
- 90일 조율 공개 창
- CVE — 메인테이너가 GHSA로 직접 발행 시 크레딧 표기 + draft collaborator 요청, D+45까지 미발행 시 MITRE 직접 신청
- 10/17 내부 성과발표 사전 고지 (재현 자료 배제, 녹화 가능성·비밀유지 미보장 명시)
- 논문 게재 가능성 사전 고지 (미확정, 게재 시 사전 draft 공유)

---

## 예정 마일스톤

| 날짜 | D+ | 이벤트 | 상태 |
|---|---|---|---|
| 2026-09-07 | D+0 | 메인테이너 3인 비공개 신고 발송 | ✅ 완료 (첨부 8건 전달 확인) |
| 2026-09-21 | D+14 | 무응답 시 1차 리마인드 | ⬜ |
| 2026-10-07 | D+30 | 무응답 시 2차 리마인드 (마지막) | ⬜ |
| 2026-10-17 | D+40 | 화이트햇스쿨 내부 성과발표 — **재현 자료 배제 원칙 적용** | ⬜ |
| 2026-10-22 | D+45 | GHSA 미발행 시 MITRE CVE 직접 신청 트리거 | ⬜ |
| 2026-12-06 | D+90 | 조율 공개 마감일 | ⬜ |

---

## 대외 공개 금지 기간

**2026-09-07 ~ 2026-12-06** (또는 패치 배포 시점 중 빠른 쪽까지)

팀 전체 적용. velog / GitHub public repo / LinkedIn / X / 발표자료 온라인 업로드 전부 포함.
10/17 발표 자료도 오프라인 발표까지만 허용, 업로드 금지.
