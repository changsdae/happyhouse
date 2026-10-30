# 응시환경 확인 목록

실제 사용할 응시환경에서 **가져오기 → 준비 → 검사 → 로컬 커밋**까지 한 번 확인한다. 내 컴퓨터에서 성공한 결과와 구분하며, 시험에서 허용된 시점에 진행한다. 문제 풀이를 시작하기 전의 준비 확인이며 제품 기능 검증은 별도다.

## 한눈에 확인

아래 표는 아직 실행하지 않은 확인 목록이다. 실제 결과는 Workspace의 `docs/ENV_CHECK.md`에 이 표를 복사해 기록한다. 내려받은 `_harness/happyhouse/` 원본에는 체크하지 않는다. 이 기록은 준비용이며 `check.py`의 필수 입력은 아니다.

- 확인 환경 / 시각 / 확인자: 미기록
- Workspace 절대 경로 / 하네스 커밋: 미기록

| 확인 | 항목 | 통과 기준 | 결과·근거 / 다음 행동 |
|---|---|---|---|
| [ ] | GitHub에서 가져오기 | 고정 경로에 키트가 있고 START.md를 읽을 수 있음 | 미실행 |
| [ ] | 실행 도구 | Git 사용 가능, Python 3.9 이상 | 미실행 |
| [ ] | 검사 도구 자체 테스트 | 실패 없이 OK, 건너뛴 항목은 별도 기록 | 미실행 |
| [ ] | 작업 준비 | SETUP 후 ready 통과, 기존 파일 보존 | 미실행 |
| [ ] | 두 세션 연결 | 같은 Workspace에서 같은 PLAN 내용을 읽음 | 미실행 |
| [ ] | 로컬 Git 기록 | 별도 연습 저장소에서 변경 확인·커밋·조회 성공 | 미실행 |

실행하지 않은 항목은 체크하지 않는다. 실패·미실행·해당 없음은 이유와 다음 행동을 남긴다. 필요한 준비가 해결되지 않았다면 ‘전체 준비 완료’로 표시하지 않는다.

## 1. Workspace에서 가져오기

아래는 **터미널 셸 명령**이다. 먼저 문제·코드가 있는 Workspace인지 확인한다.

```sh
pwd
git --version
```

`_harness/happyhouse/`가 아직 없을 때만 실행한다.

```sh
git clone https://github.com/changsdae/happyhouse.git _harness/happyhouse
```

이미 받았다면 다시 clone하지 않는다. AI에게 현재 원격 주소·변경 여부·최신 상태를 확인시킨다. 갱신이 필요하면 원본 변경과 진행 중 작업이 없는지 확인한 뒤 README의 갱신 절차를 따른다. 시험 도중 무조건 최신 버전으로 바꾸지는 않는다.

```sh
git -C _harness/happyhouse remote -v
git -C _harness/happyhouse log -1 --oneline
```

원격 주소가 `https://github.com/changsdae/happyhouse.git`인지 확인하고 START.md를 연다. 공개 저장소를 HTTPS로 내려받는 데는 일반적으로 GitHub 로그인이 필요하지 않다. 웹페이지가 열리는 것만으로 터미널 다운로드까지 확인된 것은 아니다.

## 2. 검사 프로그램 실행 확인

Workspace에서 실행한다.

```sh
python3 --version
python3 -m unittest discover -s _harness/happyhouse/tests -v
```

Python 3.9 이상이어야 한다. v2.1 기준 26개 테스트가 실행되며 마지막에 `OK`가 나와야 한다. 실행 개수와 실패·건너뜀 여부를 함께 기록한다. 테스트는 임시 폴더를 사용하며 시험 제품을 구현하지 않는다. 이후 키트 버전에서는 테스트 개수가 달라질 수 있다.

`python3`가 없는 환경에서는 `python` 또는 `py -3`의 버전을 먼저 확인하고 같은 명령을 적용한다. 사용 가능한 Python이 없으면 ‘자동 검사 미실행’으로 남기고 환경에서 허용하는 해결 방법을 확인한다.

## 3. 실제 시작 요청과 두 세션 확인

1. 주담당 AI 채팅에 [START.md](START.md)의 **‘주담당 첫 요청 — 준비’**를 전달한다. AI가 [SETUP.md](SETUP.md)에 따라 Workspace의 없는 폴더·문서만 만든다.
2. 주담당이 아래 준비 검사를 실행한다. 폴더를 만들기 전 실행해서 나오는 ‘문서 없음’은 먼저 SETUP으로 해결한다.

```sh
python3 _harness/happyhouse/check.py ready
```

3. 기존 지침·README·코드가 보존됐는지 주담당이 변경 내용을 확인한다. 아직 라운드가 정해지지 않았다면 R1 폴더나 가짜 승인·통과 결과를 만들 필요가 없다.
4. 두 터미널의 AI에게 각각 `pwd` 결과와 `docs/PLAN.md`의 현재 목표를 읽어달라고 한다. 두 세션이 **같은 절대 경로와 같은 파일 내용**을 보고 있어야 한다. 목표가 비어 있으면 둘 다 ‘미정’이라고 읽는 것이 맞다.
5. 에디터에서 PLAN의 Markdown 미리보기를 연다. 검증담당의 실제 계획 검토는 계획 초안이 나온 뒤 시작한다.

`ready` 통과는 기록 준비 확인이다. Streamlit 등 제품의 설치·실행, 브라우저 접속, 기능 정답은 실제 과제의 실행 절차로 따로 확인한다.

## 4. 로컬 Git 커밋 연습

아래는 **주담당 AI 채팅에 보내는 요청**이다.

```text
[요청] 응시환경의 Git 기록 기능을 확인해줘.
Workspace에서 실제 작업 저장소 루트와 작성자 설정을 읽기만 해서 확인해줘.
제품 저장소와 _harness/happyhouse를 구분하고, 저장소가 없으면 없다고 알려줘.
별도의 임시 연습 저장소에서 파일 하나 생성 → 수정 → git diff 확인 → 로컬 커밋 → git log 조회까지 진행해줘.
작성자 이름·이메일은 기존에 확인된 값을 사용하고, 없으면 그 부분만 나에게 물어봐.
설정이 필요하면 연습 저장소에만 적용하고 전역 설정·기존 저장소 설정은 바꾸지 마.
실제 제품 저장소에서도 커밋에 필요한 설정이 있는지 별도로 알려줘.
GitHub로 push하지 말고 결과·근거·연습 경로를 docs/ENV_CHECK.md에 남겨줘.
```

로컬 커밋은 GitHub 로그인 없이 가능하며 작성자 설정은 별개다. 연습 저장소에서의 성공이 제품 저장소의 권한·훅·서명 설정까지 보장하지는 않는다. 제품 저장소의 첫 실제 커밋도 결과를 확인한다. 외부 push는 실제 제출 방식에서 필요하고 허용될 때 별도로 확인한다.

## 막혔을 때

| 상황 | 다음 행동 |
|---|---|
| clone 실패 | 오류 문구를 AI에게 전달해 경로 중복·주소·네트워크·권한을 구분한다. 중복 폴더를 지우거나 인증 설정을 임의로 바꾸지 않는다. |
| 테스트 실패·건너뜀 | 해당 테스트 이름·오류·Python 버전을 남긴다. 원인과 환경상 제한을 확인하고 전체 성공으로 뭉뚱그리지 않는다. |
| ready 실패 | 누락된 문서·구조를 SETUP과 대조해 보완하고 다시 실행한다. |
| 커밋 실패 | 작성자 설정·쓰기 권한·훅·서명 등 실제 오류를 확인한다. GitHub 재로그인이 해결책이라고 단정하지 않는다. |

참고: [GitHub 저장소 가져오기](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository), [Git 작성자 이름](https://docs.github.com/en/get-started/git-basics/setting-your-username-in-git), [Git 커밋 이메일](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address).
