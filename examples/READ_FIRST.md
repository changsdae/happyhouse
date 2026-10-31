# SQLite 화면 예시

workspace/docs/PLAN.md와 workspace/works/R1/WORK.md를 나란히 연다. 세 번째 화면은 R1/validation/CHECK.md다.

가상 주문 점검 문제의 계획·검사 설계만 기록했다. 실제 제품·승인·검증 실행은 없다. 모든 실행 결과는 미실행이다. WORK의 ‘직접 확인 1’은 사람의 행동 순서이며 CHECK 02와 연결되는 예시다.

예시 SQLite는 로컬 ZIP에 포함한다. Git에서 DB가 없는 상태로 받으면 키트 루트에서 다음으로 복구할 수 있다:

```sh
python3 check.py restore --workspace examples/workspace --file examples/workspace/.happyhouse/state-export.json
python3 check.py render --workspace examples/workspace
python3 check.py ready --workspace examples/workspace
```

이미 DB가 있으면 restore를 반복하지 않는다. 이 예시의 check --all은 의도적으로 실패한다. 실제 실행 근거·승인·자체 테스트가 없기 때문이다. 예시 DB를 실제 시험 Workspace로 복사하지 않는다. 새 작업은 init부터 시작한다.
