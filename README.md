# Happyhouse 3.1

**사람은 Markdown을 보고, AI는 SQLite에 상태를 기록한다.**

문제 이해 → 계획 검토 → 구현·자체 테스트 → 직접 확인 → 독립 검증 → 완료 검사.

웹 대시보드나 HTML 화면을 사용하지 않는다. 두 AI 세션과 Markdown 미리보기로 진행한다. SQLite는 뒤에서 기록을 관리하며 사람이 직접 열 필요는 없다.

## 가져와서 시작하기

문제와 코드가 있는 **Workspace**에서 한 번 실행한다.

```sh
git clone https://github.com/changsdae/happyhouse.git _harness/happyhouse
```

이미 받았다면 다시 clone하지 않는다. 이전 키트에 수정한 내용이 없는지 확인한 뒤 필요한 경우 `git -C _harness/happyhouse pull --ff-only`로 갱신한다. **2.x/3.0 작업 기록은 3.1과 자동 호환되지 않는다. 3.1은 새 Workspace에서 시작한다.**

두 터미널 모두 같은 Workspace를 연다. [START.md](START.md)의 해당 요청을 AI 채팅에 전달한다. 주담당이 폴더·SQLite·문서를 준비한다. 사람이 mkdir나 DB 명령을 따로 수행할 필요는 없다. 제공된 README·AGENTS·데이터와 내려받은 키트 원본은 보존한다.

## 내가 볼 화면

| 시점 | 주로 보는 파일 | 내가 하는 일 |
|---|---|---|
| 문제 이해 | docs/PROBLEM.md | 만들 것·필수조건·데이터·미확정 내용 이해 |
| 전체 계획 | docs/PLAN.md | 라운드 목표·시간 배분·선행 관계 확인 |
| 현재 작업 | works/R1/WORK.md | 문제·선택지 이해, 질문에 답하기 |
| 직접 확인 | 같은 WORK.md | 구체적인 행동 수행, 된다/안 된다/기타 + 메모 |
| 독립 검증 | works/R1/validation/CHECK.md | 실패 내용과 다음 수정 확인 |
| 대기·최종 복습 | docs/REVIEW.md | 실제 동작·선택 이유·한계를 내 말로 설명 |

평소에는 **PLAN + 현재 WORK**, 세 번째 화면은 상황에 따라 **CHECK 또는 REVIEW**를 연다. 긴 대화·승인·실행법·변경 근거는 RECORD에 두고 필요할 때만 본다.

[PLAN 예시](examples/workspace/docs/PLAN.md) · [WORK 예시](examples/workspace/works/R1/WORK.md) · [CHECK 예시](examples/workspace/works/R1/validation/CHECK.md)

예시는 가상 주문 점검 문제의 계획이다. 실제 서비스·승인·검증 실행은 없으며 모든 검사 결과는 미실행이다.

## 한 라운드의 진행

1. **이해:** 주담당이 무엇을 왜 만드는지 설명한다. 중요한 방법은 근거·기대효과·시간·위험을 비교한다.
2. **결정:** 내가 선택 이유와 구현 범위를 전달한다. “이 범위로 구현해줘”가 실행 허용이며 “읽었다”와 구별한다. 실제 승인자·범위·발화 근거를 기록한다.
3. **구현:** 주담당이 작은 단위로 개발·자체 테스트한다. R2는 R1 결과에 연결하면서 진행한다.
4. **직접 확인:** WORK의 시작 조건·행동·기대 결과를 따라 확인한다. 체크·메모는 보존한다. 미체크는 미확인이다.
5. **검증:** 검증담당이 구현 열람 전에 작성한 기대결과로 실제 실행한다. 원문·손계산·사용 흐름 등 서로 다른 근거도 대조한다.
6. **수정:** 실패 묶음을 주담당에게 전달한다. 같은 사례 자체 테스트 후 실패·영향 범위만 재검증한다. 같은 실패가 반복되면 입력·환경·코드·기대 해석부터 대조한다.
7. **완료:** 검증담당의 기록 검사 후 주담당이 complete를 실행한다. 필요한 근거가 충족되어야 완료 상태를 저장한다. REVIEW·RESUME·관련 로컬 Git 기록도 마무리한다.

검증 중에는 검사 대상 코드·데이터·설정을 고정한다. 나는 REVIEW 복습 또는 다음 문제의 질문 준비를 한다. 두 세션은 자동으로 상대에게 일을 보내지 않는다. “CHECK를 읽고 수정해줘”처럼 전달한다. 세 번째 AI는 선택 사항이며 설명·질문 준비만 맡긴다.

## SQLite가 관리하는 것

- 요구사항 → 담당 라운드 → 검사 사례 → 실행 근거의 연결.
- 라운드 선행 관계와 선행 라운드의 검사 입력 범위.
- 현재 상태·실행 이력·기준·기록자·기록 시각.
- 오래된 상태를 덮어쓰는 요청, 누락된 연결, 변경된 코드·근거의 검사.

PLAN 표·기능 체크리스트, WORK 진행, CHECK 판정·사례·기준은 SQLite에서 생성한다. 문제 설명·질문·사람 체크·메모는 Markdown에 남긴다. 코드 변경은 **다음 status/render/check 시점**에 확인한다. 상시 감시 프로그램은 아니다.

검사기가 실제 테스트·승인·이해 확인을 대신하지 않는다. 모든 원문 요구가 등록됐는지와 검증 근거의 타당성은 검증담당이 확인한다. 역할 옵션은 운영 구분이며 사용자 인증 기능은 아니다.

## Markdown 미리보기

`<!-- happyhouse:plan:end -->` 같은 표시는 자동 갱신 영역의 경계다. 원문에는 남고 일반적인 Markdown 미리보기에서는 숨겨진다. 뷰어에 따라 보일 수 있다. 직접 지우지 않는다.

하네스의 **render 명령은 DB에서 Markdown 내용을 갱신하는 것**이다. 편집기의 **Markdown 미리보기는 그 파일을 표·제목으로 표시하는 것**이다. 서로 다른 기능이다. 사람이 보는 파일 형식은 Markdown으로 유지한다.

## 작업 구조

```text
Workspace/
├── 제공 README·AGENTS·데이터·제품 코드
├── _harness/happyhouse/          내려받은 키트 원본
├── docs/
│   ├── PROBLEM.md               문제 이해
│   ├── PLAN.md                  전체 진행
│   ├── PLAN_REVIEW.md           계획 독립 검토
│   ├── REVIEW.md                이해·복습
│   └── RESUME.md                최신 재개 정보
├── works/R1/
│   ├── WORK.md                  현재 작업·직접 확인
│   ├── RECORD.md                결정·승인·실행법·결과
│   └── validation/
│       ├── CHECK.md             검증 결과
│       └── runs/                기준 JSON·실행 로그
├── dump.md                      자유 메모
└── .happyhouse/                 SQLite·자동 내보내기
```

라운드는 계획 후 생성한다. 실제 산출 파일이 있을 때만 해당 라운드에 outputs를 추가한다. 제품 코드는 프로젝트의 기존 구조에서 누적 구현한다.

## 안내 문서

- **사람:** [START.md](START.md) 요청문 · [USER_GUIDE.md](USER_GUIDE.md) 행동 순서
- **AI:** [AGENTS.md](AGENTS.md) 공통 규칙 · [SETUP.md](SETUP.md) 준비 · [CHECKER.md](CHECKER.md) 검사 시점 · [STATE.md](STATE.md) 기록 형식
- **역할:** [주담당](roles/MAIN.md) · [검증담당](roles/VALIDATOR.md) · [선택적 준비담당](roles/PREP.md)
- **선호:** [PREFERENCES.md](PREFERENCES.md). 문제에 맞는 웹 개발은 Python + Streamlit을 우선 검토한다. 하네스 기록 DB와 제품 DB 선택은 별개다.

Python 3.9+와 표준 sqlite3만 필요하다. 추가 패키지·웹 서버·네트워크 없이 검사할 수 있다. 제품 언어는 자유다.

## 기록 보존과 개발 검증

`.happyhouse/state.sqlite3`가 작업 중 원본이다. `.happyhouse/state-export.json`은 기록 갱신 때 생성하는 Git·복구용 복사본이다. DB 자체는 Git에서 제외하고 내보내기·Markdown·관련 코드·안전한 검증 근거를 함께 기록한다. 복구 방법은 [CHECKER.md](CHECKER.md)에 있다.

```sh
python3 -m unittest discover -s tests -v
```

키트 3.1 · 2026-11-01. 기존 2.1 PDF는 이 버전의 안내가 아니다. 시험 원문·개인정보·비밀·실제 작업 로그를 공개 키트에 넣지 않는다. 시험의 도구·통신·제출 규칙을 우선한다. 라이선스는 아직 지정하지 않았다.
