# 검사 순서 · AI용

사람이 명령을 외울 필요는 없다. **check.py가 단일 진입점**이다. 아래 명령은 Workspace에서 실행한다. 기록자에는 실제 사용하는 이름을 넣는다. SQLite 기록 형식은 STATE.md에 있다.

| 시점 | 담당 | 실행 |
|---|---|---|
| 처음 준비 | 주담당 | `python3 _harness/happyhouse/check.py init` |
| 구조 확인 | 주담당 | `python3 _harness/happyhouse/check.py ready` |
| 기록 전 최신 상태 | 둘 다 | `python3 _harness/happyhouse/check.py status` |
| 계획·사례·결과 기록 | 해당 담당 | `python3 _harness/happyhouse/check.py apply --file .happyhouse/requests/요청.json --actor 이름 --role main또는validator` |
| 기대결과 작성 후, 실행 직전 | 검증담당 | `python3 _harness/happyhouse/check.py capture R1 --actor 이름 --role validator` |
| 코드·설명·사람 체크 변경 후 | 둘 다 | `python3 _harness/happyhouse/check.py render` |
| 완료 후보 | 검증담당 | `python3 _harness/happyhouse/check.py check R1` |
| 완료 상태 반영 | 주담당 | `python3 _harness/happyhouse/check.py complete R1 --actor 이름 --role main` |
| 전체 제출 전 | 주담당 | `python3 _harness/happyhouse/check.py check --all` |

다른 위치에서는 `--workspace 실제경로`를 추가한다. ready는 기록 구조만 확인한다. status는 현재 부족한 점을 보여주지만 통과 명령이 아니다. check/complete가 실패하면 종료코드 1이다. 명령 인자 오류는 2다. check는 읽기 전용이며 실제 제품 테스트를 대신 실행하지 않는다.

## 한 라운드

1. 주담당: 원문 요구를 등록하고 WORK에 문제·이유·질문 정리. RECORD에 실제 선택·승인 범위·계획 기준·완료조건 작성.
2. 검증담당: 구현 내부를 보기 전에 case에 행동·기대·원문 근거·요구사항 연결 등록. config에 코드·테스트·원문·설정·고정 입력 경로 등록. review에 독립 작성 여부와 이유 기록.
3. 주담당: 작은 단위 구현·자체 테스트. 실제 자체 테스트 로그를 보존하고 self_test 기록. WORK에 사람이 수행할 구체적인 행동 작성.
4. 검증담당: capture → 실제 테스트 실행 → 새 로그 저장 → run 기록. 실제 결과는 미실행·통과·실패·실행 불가를 구분. 통과를 추정하지 않는다.
5. 검증담당: 실행 후 코드 연결·원문·다른 방식의 근거를 대조. 수정 요청은 CHECK 수동 영역에 묶어서 작성. 기록까지 검토한 후 review.records_ok=true. check R1 실행.
6. 주담당: 검사 통과 후 complete R1. 내부에서 다시 검사한 뒤에만 완료를 저장한다. REVIEW·RESUME·관련 Git 기록을 마무리한다.

check R1은 이미 완료로 기록한 라운드도 다시 확인한다. complete는 대상과 선행 관계를 검사한다. check --all은 모든 라운드·요구 연결·제품 파일 범위·문서·근거를 확인한다. 최종 실제 사용자 흐름 검사는 별도 사례로 등록해 직접 실행해야 한다. 각 라운드 통과만으로 통합 테스트가 수행되지는 않는다.

## 코드 변경과 재검증

- status/render/check는 현재 파일 해시와 기준을 비교한다. 수정 뒤 기존 통과를 현재 통과로 표시하지 않는다.
- 하위 라운드의 검사 범위에는 선행 라운드의 입력 경로도 포함한다. 공유 코드 변경은 하위 라운드에도 재검증 필요로 나타난다.
- 실패 수정 후 주담당이 같은 사례 자체 테스트 → 검증담당 새 capture → 실패·영향 검사 실행 → 새 run 기록.
- 영향이 없는 기존 실행을 유지하려면 reuse를 기록한다. 기존 실행 시각·기준·로그는 보존한다. 현재 기준·변경 파일 전체·검토자·구체적 이유가 필요하다. 의존 파일 변경은 재실행해야 한다.
- 요구사항·라운드 목표·선행 관계·검사 구성 변경은 보수적으로 해당 라운드 검사 전체를 다시 요구한다. 제목·시간 배정 중 시간만 바뀐 경우는 검사 의미에 영향을 주지 않는다.
- 새 제품 파일이 검사 범위와 연결되지 않으면 완료가 막힌다. 기본 제외는 관리 문서·키트·DB·일반 의존성 폴더다. 추가 제외는 config.exclude와 실제 exclude_reason으로 명시한다.

## 기준과 근거

capture는 현재 파일 해시·계획 개정·RECORD 요구 조건·사례 기대조건을 DB에 보관하고 runs/basis-0001.json 형태로도 남긴다. 테스트 실행·코드 백업이 아니다. JSON 자체를 실행 로그로 쓰지 않는다.

run에는 실제 실행 시각·기준·의존 파일·로그·기대와 비교한 실제 결과를 기록한다. 로그에는 명령·입력·실행 환경·실행자·시각·종료코드를 남긴다. 각 실행은 새 파일로 저장한다. 이전 실패 로그를 수정하거나 지우지 않는다. 실행 근거 해시가 달라지면 통과를 인정하지 않는다.

사람의 안 된다/기타·복수 선택은 완료를 막는다. 직접 확인 미체크는 미확인으로 남으며 자동 검사 통과로 바꾸지 않는다. 필수 수동 검사라면 이를 별도 요구·검사 사례로 등록하여 미실행이 완료를 막도록 한다. 실제 답변과 해결 근거 없이 기존 실패를 지우지 않는다.

## 복구

- DB는 저장됐지만 Markdown 저장이 실패한 경우: status 확인 → render. 같은 요청을 무조건 다시 실행하지 않는다.
- 생성 영역을 실수로 편집했거나 중단으로 화면이 어긋난 경우: 내용을 확인한 뒤 `render --repair`. 원문을 `.happyhouse/recovery/`에 백업하고 생성 영역만 복구한다. 사람 영역은 보존한다. 경계 표시가 삭제됐으면 자동 복구하지 않는다.
- DB가 없는 복구 환경: 코드·Markdown·runs·state-export.json을 함께 복원한 뒤 `python3 _harness/happyhouse/check.py restore --file .happyhouse/state-export.json`. 기존 DB는 덮어쓰지 않는다. render → check로 현재 코드와 근거를 다시 확인한다.

이 검사는 기록의 연결과 일관성을 점검한다. 모든 원문 요구가 등록됐는지, 검사 범위가 충분한지, 로그가 진실인지, 역할 이름이 실제 사람인지까지 증명하지 않는다. 검증담당의 독립 원문 검토가 계속 필요하다.
