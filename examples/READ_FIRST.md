# SQLite 화면 예시

workspace/docs/PLAN.md와 workspace/works/R1/WORK.md를 나란히 연다. 검사 근거를 보고 싶을 때만 R1/validation/CHECK.md를 연다. 기본 화면은 두 개다.

가상 주문 점검 문제의 계획·검사 설계만 기록했다. 실제 제품·승인·검증 실행은 없다. 모든 실행 결과는 미실행이다. WORK의 ‘직접 확인 1’은 사람의 행동 순서이며 CHECK 02와 연결되는 예시다.

예시는 복구용 JSON을 포함한다. DB가 없는 상태로 받으면 키트 루트에서 다음으로 복구할 수 있다:

```sh
python3 check.py restore --workspace examples/workspace --file examples/workspace/.happyhouse/state-export.json
python3 check.py render --workspace examples/workspace
python3 check.py ready --workspace examples/workspace
```

이미 DB가 있으면 restore를 반복하지 않는다. 이 예시의 check --all은 의도적으로 실패한다. 실제 실행 근거·승인·자체 테스트가 없기 때문이다. 예시 DB를 실제 시험 Workspace로 복사하지 않는다. 새 작업은 init부터 시작한다.

## 합성 회귀 테스트 세트 예시

[입력 CSV](capacity-cases.csv)는 같은 평균 수요에서 쏠림만 바꾼 가상 입력이다. 예제 규칙은 정류장마다 지정 차량 한 대, 정류장 간 이동·재배치 없음이다. 기대값은 정류장마다 수요와 좌석 중 작은 수를 더해 구한다.

| 사례 | 평균 수요 | 기대 탑승 | 기대 미탑승 |
|---|---|---|---|
| even | 10 | 30 | 0 |
| peak | 10 | 24 | 6 |

실제 과제에서는 허용된 배차·이동 규칙과 데이터 스키마에 맞춰 만든다. 수정 전후 같은 사례를 실행할 때 입력 파일과 기대값을 함께 고정한다.
