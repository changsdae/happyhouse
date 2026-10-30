# 상태 갱신 명령 — 담당 AI용

아래 명령은 모두 Workspace에서 실행합니다. 사람에게 매번 입력하게 하지 말고 담당 AI가 수행합니다. Python 3.10 이상, 외부 의존성 없음.

```sh
python3 _harness/happyhouse/happyhouse.py init
python3 _harness/happyhouse/happyhouse.py configure --title '실제 과제 이름' --approver '실제 승인자' --total-minutes 180 --planning-minutes 20 --reserve-minutes 30
```

예시의 이름/목표는 실제 대화로 교체합니다. 초기화만 할 때 라운드를 미리 만들지 않습니다. init 재실행은 사용자 본문·기존 dump·기록을 보존하고 표만 동기화합니다. 기존 파일이 충돌하면 중단하므로 파일을 삭제하지 말고 내용을 확인해 사람이 결정하게 합니다.

## 라운드 계획

```sh
python3 _harness/happyhouse/happyhouse.py add-round R1 --title '첫 기능' --goal '구체적인 구현 과제' --done-when '관찰 가능한 완료조건'
python3 _harness/happyhouse/happyhouse.py update-round R1 --minutes 35 --difficulty 중 --reason '목표 구체화 후 시간 배정'
python3 _harness/happyhouse/happyhouse.py add-round R2 --title '다음 기능' --goal 'R1에 연결할 과제' --done-when '누적 완료조건' --depends R1 --minutes 40
python3 _harness/happyhouse/happyhouse.py select R1
python3 _harness/happyhouse/happyhouse.py status R1 --set implementing --note '승인 근거는 WORK의 R1-02'
```

`add-round`가 works/validation/results에 라운드 폴더와 문서를 만듭니다. 시간이 미정이면 --minutes를 생략합니다. PLAN 표는 등록 순서의 순차 실행 목표입니다. 기본 예산에서 R1 35분이면 계획20+구현35 경과 후 `02:05:00`입니다.

`update-round`는 같은 라운드 ID를 유지하고 개정을 올립니다. 기존 값은 자동 events 이력에 남습니다. 시간·제목만 바뀐 경우에도 보수적으로 재검토 표시를 합니다. 해당 라운드와 이를 선행으로 삼는 라운드는 재검증 필요로 전환됩니다. 구체적인 논의와 재승인 필요 여부는 WORK에서 별도로 판단합니다.

## 코드 기준과 검증

```sh
python3 _harness/happyhouse/happyhouse.py checkpoint R1 --basis '실제 코드 커밋 SHA 또는 재현 가능한 해시 목록 식별값'
python3 _harness/happyhouse/happyhouse.py show
```

검증 시작 전에 실제 코드 기준을 등록하고 변경을 멈춥니다. `show`의 revision과 basis를 확인해 검증 기록과 맞춥니다. 미커밋 변경이 있으면 커밋 SHA만으로 현재 코드를 표현할 수 없습니다. 관련 변경을 포함한 커밋 또는 파일 해시 목록을 근거로 사용합니다.

현재 구현은 코드 파일 변화를 자동 감시하지 않습니다. **관련 코드가 바뀔 때마다 checkpoint를 다시 실행해야 합니다.** 문서만 추가한 커밋은 마지막 코드 기준과 구분해서 설명합니다. 선행 변경은 후속 라운드를 재검토 상태로 만듭니다. 이번 라운드의 변경이 선행 기능에 영향을 주면 그 선행 라운드의 기준도 갱신하여 재검증합니다.

실제로 테스트한 후 검증담당이 실행합니다. 아래 2는 예시이므로 현재 개정 번호로 바꿉니다.

```sh
python3 _harness/happyhouse/happyhouse.py check R1 --result pass --revision 2 --basis '위와 동일한 실제 코드 기준' --evidence validation/R1/runs/01.txt --by '검증담당 세션 이름'
python3 _harness/happyhouse/happyhouse.py status R1 --set done --note '현재 코드 검증·통합 완료; SUMMARY 갱신'
```

`--result`는 pass/fail/blocked입니다. evidence는 실제 내용이 있는 Workspace 내부 파일이어야 합니다. 명령은 내용의 진실성까지 판정하지 않습니다. 계획 개정·코드 기준이 현재와 다르면 기록을 거절합니다. `done`은 현재 기준의 pass와 선행 라운드 완료가 있어야 가능합니다. 승인과 별개입니다.

상태: planning / ready / implementing / validating / fixing / done / blocked.
이름은 도구 내부 값이고 화면에는 한국어로 나옵니다. 별도 R/W/D/T 라벨을 만들지 않습니다.

## 타이머와 화면

```sh
python3 _harness/happyhouse/happyhouse.py timer start --remaining 03:00:00
python3 _harness/happyhouse/happyhouse.py timer sync --remaining 02:40:00
python3 _harness/happyhouse/happyhouse.py serve
```

실제 시작 요청 때만 start합니다. 플랫폼 타이머가 우선이며 실제 값으로 sync합니다. 서버/페이지를 다시 열어도 기한을 유지합니다. 전체 제한시간을 바꾸려면 configure를 먼저 사용합니다. 기본 서버는 127.0.0.1:8765, 로컬 읽기 전용이며 외부로 데이터를 전송하지 않습니다. 실제 시험의 미리보기에서 별도 바인딩이 필요할 때만 허용된 환경의 안내를 따릅니다.

## 두 세션의 파일 소유권

주담당: PLAN 본문·WORK·SUMMARY·제품 코드. 검증담당: PLAN_REVIEW·CHECK·runs.
자동 상태 `.happyhouse/state.json`과 PLAN의 자동 표 구간은 직접 고치지 말고 명령을 사용합니다. 같은 순간 갱신하면 잠금으로 거절되므로 잠시 뒤 재시도합니다. 중단된 잠금은 기록된 PID가 실제 실행 중이 아닌지 확인한 뒤에만 제거합니다.

자동 표 표시를 지웠다면 PLAN 본문을 보존하며 `<!-- happyhouse:overview:start -->`와 `<!-- happyhouse:overview:end -->`를 복원한 뒤 sync합니다. state는 메타데이터 기준, PLAN 자동 표는 그 투영입니다. 본문과 CHECK의 내용은 AI가 직접 갱신해야 합니다.

## Git과 인계

코드·대화·검증 근거를 의미 있는 단위로 로컬 커밋하고 이유가 드러나는 메시지를 씁니다. 예: `R1: 빈 입력 처리와 연결 검증 추가`. 전체 폴더를 무조건 stage하지 않습니다. `.happyhouse/state.json`과 events 이력은 필요하면 함께 기록하고 일시적 write.lock은 넣지 않습니다. 하네스는 Git 명령을 자동 실행하지 않습니다.

원본 키트 저장소와 시험 제품 저장소는 별개입니다. 개인 메모·문제·데이터·실행 로그가 원본 하네스 원격에 push되지 않게 대상 저장소를 확인합니다. 제품 Git 작성자 정보가 없으면 사용자에게 확인합니다.

다른 위치에서 도구를 시험할 때만 `python3 happyhouse.py --workspace /실제/작업폴더 init`처럼 전역 `--workspace`를 **하위 명령 앞**에 씁니다. 정상 배치 `_harness/happyhouse`에서는 경로를 입력할 필요가 없습니다.
