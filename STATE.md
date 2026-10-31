# SQLite 기록 · AI용

사람은 PLAN·WORK·CHECK를 읽는다. AI만 아래 형식을 사용한다. DB를 직접 SQL로 수정하지 않는다. 기록 요청은 `.happyhouse/requests/`에 저장한다. Python 표준 라이브러리만 필요하다.

## 원본 구분

| 원본 | 내용 |
|---|---|
| SQLite | 라운드 목표·시간·상태, 요구사항·출처, 선행 관계, 검사·요구 연결, 기준, 실행 이력, 영향 없는 실행의 유지 검토, 기록 이벤트 |
| Markdown | 문제 설명·선택·승인 발화·원문 해석·질문·직접 체크·메모·복습·인계 |
| runs 파일 | 실행 로그·기준 JSON. 한 번 만든 근거를 덮어쓰지 않는다. |

PLAN 전체 진행표·완료할 기능, WORK 진행, CHECK 판정·검사 항목·검사 기준·실행 근거는 자동 생성 영역이다. 직접 고치지 않는다. HTML 주석 경계는 미리보기에서 숨겨진다. 생성 영역 이외에는 자유롭게 짧은 내용을 작성한다. WORK 사람 체크는 DB와 이중 편집하지 않으며 완료 검사 때 Markdown에서 읽는다.

## 기록 방법

1. `check.py status`로 최신 revision 확인.
2. 아래 JSON의 revision을 실제 값으로 작성.
3. `check.py apply --file .happyhouse/requests/고유이름.json --actor 실제이름 --role main` 또는 validator 실행.
4. 다른 기록이 먼저 저장됐다는 오류면 status로 다시 읽고 의도를 재검토. 숫자만 무조건 바꿔 재시도하지 않는다.

한 요청은 DB에서 전부 성공하거나 전부 취소된다. 요청 성공 후 문서를 생성한다. 문서 저장 실패 시 DB가 이미 저장됐을 수 있으므로 status → render로 복구한다. 두 담당자 DB 기록은 짧은 쓰기 트랜잭션으로 순서대로 처리된다. 제품·문서 파일의 동시 편집까지 안전하게 합치는 기능은 아니다.

## 계획 등록 예시 · main

아래는 형식 예시다. 실제 문제·승인·검증 결과로 복사하지 않는다. 경로는 source 링크가 들어갈 문서 기준이다. 요구사항 source는 docs/PROBLEM.md 기준, 검사 source는 works/Rn/validation/CHECK.md 기준이다. 원문 파일은 실제로 존재해야 한다.

```json
{
  "revision": 0,
  "operations": [
    {"op":"round","id":"R1","title":"데이터 읽기·오류 안내","budget":"보통·40분","target":"02:00:00"},
    {"op":"round","id":"R2","title":"데이터로 결과 계산","budget":"높음·45분","target":"01:15:00"},
    {"op":"requirement","id":"R1-required-columns","round":"R1","title":"빠진 필수 열 이름을 보여준다","source":"[원문](../README.md)"},
    {"op":"depends","round":"R2","on":["R1"]}
  ]
}
```

라운드 폴더는 자동 준비한다. 요구사항 하나에는 담당 라운드 하나를 지정하고 여러 검사와 연결할 수 있다. 여러 라운드에 걸친 통합 요구는 최종 통합 라운드에 배정하고 선행 관계를 연결한다. 내부 요구사항 ID는 사람 화면에 나열하지 않는다.

## 검사 준비 예시 · validator

```json
{
  "revision": 1,
  "operations": [
    {"op":"case","round":"R1","id":"01","input":"필수 price 열 없는 예제 선택 → 검증","expected":"price 열 누락 표시·기존 데이터 유지","source":"[원문](../../../README.md)","requirements":["R1-required-columns"]},
    {"op":"config","round":"R1","inputs":["src","tests","README.md"],"exclude":[]},
    {"op":"review","round":"R1","independent":true,"records_ok":false,"reason":"구현 열람 전 원문에서 기대결과 작성. 실행·영향 검토는 대기."}
  ]
}
```

config.inputs에는 실제 존재하는 파일/폴더를 지정한다. 폴더 안 신규·삭제 파일도 추적한다. exclude가 비어 있지 않으면 exclude_reason도 필수다. 범위 축소는 검증담당이 근거를 확인한다. 선행 라운드의 inputs를 합치며, 공통으로 제외된 항목만 유효 제외로 사용한다.

## 실행 기록 예시 · validator

capture 후 실제 테스트를 실행한다. run의 basis·시간·로그를 실제 실행에서 수집한다. 기본 dependencies는 현재 기준 JSON의 files 전체다. 일부만 쓰려면 공유 코드·설정·원문·입력·테스트 의존성을 확인한다.

```json
{
  "revision": 3,
  "operations": [
    {"op":"run","round":"R1","case":"01","verdict":"통과","actual":"price 열 누락 표시·기존 데이터 유지 확인","basis":"runs/basis-0001.json","ran_at":"실제 시간대 포함 ISO 시각","dependencies":["src/app.py","tests/test_input.py","README.md"],"evidence":"runs/exec-0001-case01.log"},
    {"op":"review","round":"R1","independent":true,"records_ok":true,"reason":"실제 실행·다른 근거·변경 영향·승인 범위·RECORD·RESUME를 대조한 결과와 한계"}
  ]
}
```

가상의 날짜나 이름을 쓰지 않는다. run 기록은 추가만 하며 이전 실패도 DB에 보존한다. 사례·요구사항 개정은 같은 ID를 갱신하되 원래 요청 전체가 events에 누적된다. 모든 run이 통과해도 기록·사람 관찰·현재 기준이 부족하면 complete가 실패한다.

## 지원 작업

| op | 담당 | 필드 / 의미 |
|---|---|---|
| round | main | id, title, 선택 budget/target. 추가 또는 목표 갱신 |
| requirement | main | id, round, title, source. 출처 있는 요구사항 |
| depends | main | round, on 배열. 해당 라운드 선행 관계 전체 교체·순환 금지 |
| status | main | round, value. 계획 중/구현 중/검증 중/수정 중/보류. 완료 직접 지정 금지 |
| self_test | main | round, evidence. Workspace 기준 실제 자체 테스트 로그 경로. 현재 코드·로그 해시 함께 저장 |
| case | validator | round, id, input, expected, source, requirements 배열 |
| config | validator | round, inputs, exclude, 제외 시 exclude_reason |
| review | validator | round, independent/records_ok는 true 또는 false, reason |
| run | validator | round, case, verdict=통과/실패/실행 불가, actual, basis, ran_at, dependencies, evidence |
| reuse | validator | run=기존 실행 DB 정수 ID, against=현재 기준, changed_files=변경 파일 전체 사전순, reason |

reuse의 run ID는 state-export.json의 runs에서 확인한다. 기존 실행은 바꾸지 않고 검토를 별도로 추가한다. 요구·관계·검사 구성이 바뀌었거나 의존 파일이 바뀌면 재사용할 수 없다. 다시 실행한다. 같은 파일의 동일 근거 재사용은 새로운 실행으로 꾸미지 않는다.

records_ok는 검증담당의 실제 기록 검토 선언이다. run·case·config·capture 변경 시 해제된다. 프로그램 통과를 실제 사람 승인으로 해석하지 않는다. 역할 옵션은 인증·권한 보안이 아니며, 누가 요청했는지 남기는 운영 규칙이다.

## Git과 복구

DB는 작업 중 원본, state-export.json은 자동 생성한 읽기/복구용 복사본이다. 표와 JSON을 직접 고쳐 원본으로 역수입하지 않는다. JSON은 저장소에서 이력을 읽고 DB가 없는 환경에서 restore할 때 사용한다. 여러 브랜치의 내보내기를 자동 병합하지 않는다.

restore는 DB만 재구성한다. 코드·RECORD·직접 체크·로그·기준 JSON도 함께 보존해야 실제 완료 상태를 다시 검증할 수 있다. 비밀·시험 개인정보는 내보내기·이벤트 요청·로그에 넣지 않는다.
