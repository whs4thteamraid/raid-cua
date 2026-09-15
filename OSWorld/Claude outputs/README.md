# OSWorld 취약점 신고 — 파일 정리

발견: 게스트 통제 파이썬이 평가 환경 권한으로 실행됨 (OSWorld 1.0 & 2.0)

## 01_발송_영문/  ← 메인테이너에게 첨부할 것

| 파일 | 용도 |
|---|---|
| `OSWorld_security_report.pdf` | 본문 (A4 5p). 읽기·전달·인쇄용 |
| `OSWorld_security_report.md` | 같은 내용. 검증 명령 복사용 |
| `F2_call_flow_evidence.md` | 호출 흐름 근거, 인용 행 감사표, 검증 절차 |
| `f2_upstream_verify.py` | 무패치 재현 스크립트 |
| `classify_tasks.py` | 369/215/2 영향 범위 분류 재현 |
| `hf_test.py` | HF 테스트 파일 보존 사본 (b266e832…) |
| `settings_original.py` | 원본 settings.py 보존 사본 (fca04a7c…) |
| `MANIFEST.txt` | 위 7개 파일의 sha256. 수신 측 검증용 |

총 772KB. 메일 첨부 한도에 여유.

**보내지 않는 것:** 시나리오 JSON, 페이로드, C-1 실행 산출물.
재현에 불필요하고 완성된 공격 문서를 배포하는 셈이 된다.

## 02_내부_국문/  ← 팀·멘토 공유용

| 파일 | 용도 |
|---|---|
| `OSWorld_보안신고서_국문참고본.pdf` | 국문 번역 (A4 4p). **영문본이 기준** |
| `OSWorld_보안신고서_국문참고본.md` | 같은 내용 |
| `OSWorld_disclosure_email_draft.md` | 메일 본문 + 발송 체크리스트 + 무응답 시 경로 |

## 03_내부_자료/  ← 발송 안 함

Annex B(에이전트 행동 실험) 판정기와 설명용 SVG.
Annex B 는 보고서에 요약만 싣고 원자료는 요청 시 제공한다.

## _stale/

구버전. 참조하지 말 것.

---

## 발송 절차

1. 팀·멘토에게 발송 사실 공유
2. `ksasha@ajou.ac.kr` 에서 →
   `yuanmengqi732@gmail.com`, `tianbaoxiexxx@gmail.com`, `zzl0712@connect.hku.hk`
   (V1 README:252 / V2 README:312 이 "current maintainer" 로 명시한 셋. 두 저장소를 모두 다루므로 전원 수신)
   제목: `Private security report — guest-controlled code executed with evaluator privileges (OSWorld 1.0 & 2.0)`
   본문: `02_내부_국문/OSWorld_disclosure_email_draft.md`
   첨부: `01_발송_영문/` 전부 (8개)
3. **발송 시각 기록** → D+0
4. D+3~5 Discord DM 으로 수신 확인만 (내용 없이)
5. 이후 일정은 메일 초안 하단 참조

## 채널 확인 결과 (2026-09-07)

```
SECURITY.md               없음 (두 저장소 모두)
GitHub private advisory   비활성 (/security/advisories/new 폼 없음)
메인테이너 메일            유일한 통보 채널
Discord                   리마인더 전용 — 내용 금지
```
