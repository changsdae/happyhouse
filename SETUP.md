# 준비 · 주담당 AI용

현재 작업 위치는 Workspace, 키트는 `./_harness/happyhouse/`다. 시험 제공 지침·README·코드·데이터를 먼저 확인한다. 키트 원본은 실행 대상으로만 사용한다.

1. `python3 _harness/happyhouse/check.py init` 실행.
2. `python3 _harness/happyhouse/check.py ready` 실행.
3. 원문과 데이터를 읽고 docs/PROBLEM.md 작성. 아직 PLAN 라운드·승인·구현을 가정하지 않는다.
4. 사용자가 계획으로 전환하면 STATE.md의 main 요청으로 라운드·요구사항·선행 관계 등록. 관련 폴더와 문서는 자동 생성된다.

init은 기존 파일을 초기화하지 않는다. DB가 있으면 status/render로 재개한다. 기존 라운드가 들어 있는 Markdown 전용 Workspace는 자동 이관하지 않는다. 새 Workspace에서 사용하거나 별도의 검증된 이관 작업을 수행한다.

## 실제 Workspace

```text
Workspace/
├── 제공 README·AGENTS·데이터·제품 코드
├── _harness/happyhouse/          키트 원본
├── docs/
│   ├── PROBLEM.md                문제 이해
│   ├── PLAN.md                   목표·자동 진행표·위험
│   ├── PLAN_REVIEW.md            계획 독립 검토
│   ├── REVIEW.md                 내가 이해한 내용
│   └── RESUME.md                 다음 세션 재개
├── works/R1/
│   ├── WORK.md                   문제·진행·직접 확인
│   ├── RECORD.md                 결정·승인·실행법·결과
│   └── validation/
│       ├── CHECK.md              자동 검사표 + 검증담당 수정 요청
│       └── runs/                 기준 JSON·실제 실행 로그
├── dump.md                       자유 메모
└── .happyhouse/
    ├── state.sqlite3             상태·관계 원본
    ├── state-export.json         자동 내보내기·Git 기록
    └── requests/                 AI가 작성하는 기록 요청
```

초기에는 works가 비어 있다. R1·R2는 계획 후 등록한다. 실제 출력물이 있을 때만 해당 라운드 outputs를 만든다.

## Git

기존 .gitignore를 보존하며 필요한 항목만 추가한다:

```gitignore
.happyhouse/state.sqlite3*
.happyhouse/requests/
.happyhouse/recovery/
```

내보내기·문서·관련 코드·안전한 검증 근거를 함께 로컬 커밋한다. 실제 개인정보·비밀·시험 자료를 공개 저장소에 올리지 않는다. Git 작성자를 임의 설정하지 않는다. 외부 push는 별도 허용 범위를 따른다.

PLAN 생성 영역에 직접 체크하거나 상태를 타이핑하지 않는다. WORK 직접 확인은 사람이 편집할 수 있다. 동시에 같은 Markdown 파일을 저장하지 않는다. DB는 두 담당자가 공통 명령으로 사용하며 요청 revision 충돌 시 최신 상태를 읽고 다시 작성한다.
