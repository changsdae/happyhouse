# Happyhouse

두 개의 AI 작업 세션과 사람이 함께 쓰는 가벼운 로컬 하네스입니다. **전체 계획 + 현재 라운드 작업**을 보면서 진행하고, 별도 검증 세션이 원문을 근거로 확인합니다.

Python 3.10 이상만 필요합니다. 추가 패키지·외부 API·계정 연결은 없습니다. Git은 기록용으로 별도 사용합니다.

## 1. Workspace에서 가져오기

```sh
git clone https://github.com/changsdae/happyhouse.git _harness/happyhouse
python3 _harness/happyhouse/happyhouse.py init
```

GitHub 주소는 이 문서에서 복사하면 됩니다. 암기할 필요가 없습니다. 이미 받은 폴더가 있다면 `_harness/happyhouse`에 놓고 두 번째 명령만 실행합니다.

**시험에서 내려받은 `_harness/happyhouse` 원본은 수정하지 않습니다.** 도구는 그 바깥 Workspace에 작업 기록을 만듭니다. 제공된 AGENTS.md·README.md·코드 폴더를 덮어쓰지 않습니다. 충돌하는 기존 작업 문서는 먼저 확인하도록 중단합니다.

## 2. 터미널 두 개에서 시작

두 세션 모두 같은 Workspace를 엽니다. [START.md](START.md)에 복사할 첫 요청과 재개 요청이 있습니다.

- 주담당: 원문 이해 → 계획 → 사용자 결정 → 구현·자체 테스트 → 기록·Git 커밋
- 검증담당: 원문과 계획 독립 검토 → 구현 내부를 보기 전 기대결과 작성 → 실행·근거 확인

두 세션은 파일로 인계합니다. 상대 세션이 자동으로 읽거나 실행하지는 않습니다. 사람이 “검토 파일을 읽고 반영해줘”라고 전달합니다.

## 3. 항상 볼 화면

```sh
python3 _harness/happyhouse/happyhouse.py serve
```

브라우저에서 `http://127.0.0.1:8765`를 엽니다. 대시보드는 전체 라운드 표와 `PLAN.md` / 선택한 `WORK.md`를 보여주고 3초마다 갱신합니다. 검증·결과·메모 탭도 있습니다. 읽기 전용이며 서버는 Ctrl+C로 종료합니다.

터미널 두 개를 AI에 쓰려면 주담당에게 서버를 별도 백그라운드 작업으로 실행하고 PID와 종료법을 남기라고 요청하세요. 대시보드 없이 에디터의 Markdown 미리보기 두 개만 사용해도 됩니다. 원격 시험 환경에서는 그 환경이 제공하는 로컬 앱 미리보기를 사용하세요.

Markdown 미리보기 버튼은 문서 표시용입니다. 인터랙티브 화면은 **서버를 실행한 환경 안에서** IDE 브라우저 미리보기 또는 원격 데스크톱의 Chromium으로 위 주소를 열어 확인합니다. 원격 환경에서 실행 중인 서버를 개인 PC의 localhost로 열면 다른 컴퓨터를 가리키므로 연결되지 않습니다. 시험 플랫폼의 포트 연결 방식은 사전 체험에서 확인하세요.

## 만들어지는 구조

```text
Workspace/
├── AGENTS.md, README.md, 기존 제품 코드    제공된 내용 보존
├── _harness/happyhouse/                  내려받은 원본
├── docs/
│   ├── PLAN.md                         항상 볼 전체 계획
│   └── RESUME.md                       역할별 재개 안내
├── works/R1/WORK.md                     현재 대화·결정·인계
├── validation/
│   ├── PLAN_REVIEW.md                   계획 독립 검토
│   └── R1/CHECK.md, runs/               기대결과·실행 근거
├── results/R1/SUMMARY.md                라운드 누적 결과와 실제 산출물
├── dump.md                             자유 메모
└── .happyhouse/                         자동 상태·변경 이력
```

처음에는 R1 폴더가 없습니다. 계획에서 라운드를 정하면 도구가 생성합니다. 제품 코드는 기존 구조를 따릅니다. `results/`는 코드 복제본 보관함이 아닙니다.

## 읽을 문서

- [START.md](START.md): 실제로 복사할 시작·인계 요청
- [USER_GUIDE.md](USER_GUIDE.md): 사람이 확인할 짧은 체크리스트
- [roles/MAIN.md](roles/MAIN.md), [roles/VALIDATOR.md](roles/VALIDATOR.md): 역할별 규칙
- [COMMANDS.md](COMMANDS.md): AI가 문서·상태를 갱신하는 명령

## 범위와 검증

이 도구는 상태와 증거 위치를 기록합니다. 파일이 존재한다고 내용이 정확한지, 승인자가 실제로 승인했는지 자동 판정하지 않습니다. 역할 분리는 작업 규칙이며 운영체제 수준의 접근 차단은 아닙니다. 코드 변경 후 기준 갱신과 실제 재검증은 담당자가 수행합니다.

다운로드 허용 여부와 사용 도구·통신·제출 제한은 실제 시험 지침을 먼저 따릅니다. 시험 Workspace의 문제·데이터·로그를 이 공개 하네스 저장소에 올리지 않습니다.

개발 검증:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
node tests/markdown.test.js
```

하네스 버전: 1.0.0. 제품 버전과 라운드 계획 개정 번호는 별도로 관리합니다. 라이선스는 아직 지정하지 않았습니다.

Node.js는 화면 표시 함수의 개발 테스트에만 필요하고 실제 하네스 실행에는 필요하지 않습니다.
