# E2E Tester

사내 임직원이 본인 로컬 PC에서 웹 애플리케이션을 점검하기 위해 사용하는 내부용 E2E 테스터입니다.

이 프로젝트를 내려받아 실행하면 브라우저 기반 테스트를 웹 화면에서 시작할 수 있고, 실행 상태와 로그를 확인할 수 있습니다.

## 프로젝트 소개

이 프로젝트의 목적은 다음과 같습니다.

- 사내 사용자가 직접 로컬 PC에서 웹 애플리케이션 E2E 테스트를 실행
- 테스트 진행 상태를 웹 화면에서 확인
- 실행 중 필요한 입력이 있으면 화면에서 이어서 처리
- 실행 로그와 스크린샷 결과를 로컬에 저장

현재 프로젝트는 Python 기반으로 실행되며, 로컬에서 웹 서버를 띄운 뒤 브라우저로 접속해 사용하는 방식입니다.

## 사용 대상

- 사내 임직원
- 본인 PC에 Python 설치가 가능한 사용자
- 로컬 환경에서 테스트 실행이 필요한 사용자

## 로컬 PC 실행 방법

### 1. 사전 준비

먼저 로컬 PC에 아래가 준비되어 있어야 합니다.

- Python 3 설치
- Git 설치

터미널에서 아래 명령으로 설치 여부를 확인할 수 있습니다.

```bash
python3 --version
git --version
```

### 2. 프로젝트 내려받기

원하는 작업 폴더에서 아래 명령을 실행합니다.

```bash
git clone https://github.com/lozenia64/e2eTester.git
cd e2eTester
```

### 3. 필요한 패키지 설치

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

브라우저 실행 시 코드는 로컬 Chrome 채널을 우선 사용하고, 실행이 어려우면 설치된 Playwright Chromium으로 자동 fallback 합니다.

일반 브라우저나 Cursor의 Playwright MCP와 동일하게 보안프로그램(키보드보안/백신류 로컬 에이전트·확장)을 인식시키기 위해, 브라우저를 다음과 같이 띄웁니다.

- **영속 프로파일(persistent context)**: 시크릿 일회용 컨텍스트가 아니라 영속 프로파일로 실행해 확장/인증서/권한 상태가 유지됩니다. 프로파일은 기본 `~/.e2etester/chrome-profile` 에 저장되며 환경변수 `E2E_USER_DATA_DIR` 로 경로를 바꿀 수 있습니다. 이미 보안 확장이 설치된 본인의 Chrome 프로파일을 그대로 쓰려면 해당 경로를 `E2E_USER_DATA_DIR` 로 지정하세요(같은 프로파일을 쓰는 Chrome 창이 떠 있으면 안 되고, 동시 실행도 같은 프로파일을 공유할 수 없습니다).
- **확장 활성화**: Playwright 기본값인 `--disable-extensions`(및 component-extensions) 를 제거해, 보안프로그램의 브라우저 확장이 로드되도록 합니다.
- **로컬 네트워크 허용**: 보안프로그램은 로컬 에이전트(loopback/사설망)와 통신합니다. Chrome의 Local/Private Network Access 차단 기능을 꺼서(일반 브라우저에서 "로컬 네트워크 허용"을 켠 것과 동일) 페이지가 로컬 에이전트에 접근할 수 있게 합니다.

> 참고: 위 설정에도 보안프로그램이 인식되지 않으면, 해당 보안프로그램(및 그 브라우저 확장)이 실제로 설치되어 있고, `E2E_USER_DATA_DIR` 가 그 확장이 설치된 프로파일을 가리키는지 확인하세요.

환경에 따라 `python3` 대신 회사 PC에 설치된 Python 실행 경로를 사용해야 할 수 있습니다.

예:

```bash
/usr/local/bin/python3 -m pip install -r requirements.txt
/usr/local/bin/python3 -m playwright install chromium
```

### 4. 웹 서버 실행

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python3 -m uvicorn app.main:app --reload
```

예:

```bash
/usr/local/bin/python3 -m uvicorn app.main:app --reload
```

### 5. 브라우저에서 접속

웹 브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

접속 후 웹 화면에서 테스트를 실행하면 됩니다.

## 사용 흐름

1. 홈 화면에서 테스트할 시스템을 선택하거나, 맨 위 **전체 시스템 순차 점검(SUITE)** 카드에서 여러 시스템을 한 번에 실행합니다.
2. 필요한 입력값을 작성합니다. (개별 Run은 모듈 선택, SUITE는 시스템 선택)
3. `실행` 또는 `전체 점검 시작` 버튼을 눌러 테스트를 시작합니다.
4. Run/Suite 화면에서 진행 상태, 로그, 결과를 확인합니다.
5. 추가 입력이 필요한 경우 화면 안내에 따라 계속 진행합니다. (SUITE 실행 중 OTP는 Suite 화면의 OTP 패널에서 제출)

현재 기본으로 포함된 시스템은 다음과 같습니다.

대표홈페이지(로그인·본인인증 포함 전체 점검):

- **HOM**(`대표홈페이지(PC)`): PC 웹 대표홈페이지 점검
- **MHM**(`대표홈페이지(모바일)`): 모바일 웹 대표홈페이지 점검 (Playwright로 모바일 디바이스 모드를 먼저 적용한 뒤 접속)

대표홈페이지와 별개의 업무 시스템(현재는 **메인화면 접속만** 점검, 이후 시나리오는 모듈로 하나씩 추가):

- **FP**(`영업가족 위촉서류 등록(PC)`): `https://fp.hwgeneralins.com`
- **HRP**(`현장출동 홈페이지(PC)`): `https://www.eagleprm.co.kr`
- **HWTC**(`연수원(PC)`): `https://sls.hwgeneralins.com`
- **CHBOT**(`챗봇(모바일)`): `https://chbot.hwgeneralins.com/...` (모바일 디바이스 모드 적용 후 접속)

모든 시스템은 홈 화면 카드를 펼쳐 입력값을 채우고 실행하며, 실행 전 모듈 선택 그래프에서 실행할 모듈을 개별로 선택/해제할 수 있습니다. 선택하지 않은 모듈은 Run 화면에서 `SKIPPED`(건너뜀)로 표시됩니다. FP·HRP·HWTC·CHBOT은 로그인/인증 없이 메인화면 접속 1개 모듈만 점검합니다.

### 전체 시스템 순차 점검 (SUITE)

홈 화면 맨 위 **SUITE** 카드에서 등록된 시스템을 `display_order` 순으로 **하나씩 순차 실행**할 수 있습니다. 개별 Run의 모듈 선택과 같은 패턴으로, 실행 전 **시스템 체크박스**에서 포함할 시스템만 골라 실행할 수 있습니다.

- **시스템 선택**: 기본값은 전체 선택. 체크 해제한 시스템은 Suite 결과 화면에서 `SKIPPED`(건너뜀)로 남고 Run은 생성되지 않습니다.
- **브라우저 모드**: 모든 선택 시스템에 공통 적용 (`headed` / `headless`).
- **HOM·MHM 인증**: 해당 시스템이 선택된 경우에만 인증 입력 패널이 표시·검증됩니다.
- **실패 시 동작**: 한 시스템이 실패해도 다음 선택 시스템 점검은 계속됩니다.
- **OTP**: 휴대폰인증 Run이 `WAITING_INPUT`이 되면 Suite 화면(`/suites/{suite_id}`)에서 OTP를 제출합니다.
- **예약 실행**: SUITE 카드 안에서 cron 예약을 등록할 수 있으며, 등록 시점의 **시스템 선택·브라우저 모드·HOM/MHM 인증 정보**가 함께 저장되어 예약 트리거 시 동일하게 재현됩니다. 무인 예약은 OTP 대기에서 멈출 수 있습니다.

API 요청 시 `selected_system_codes`를 생략하면 기존과 같이 전체 시스템이 선택됩니다.

### HOM 시스템

**HOM**(`대표홈페이지(PC)`) Run은 다음 순서로 모듈이 실행됩니다.

1. 메인화면 접속 → 로그인(본인인증) → 계약목록 조회 → 계약상세 조회 → 보험금청구 접수(질병/상해) → 보험금청구 결과 조회 → 보험금청구 취소 → 장기보험증권 증명서 발급

   (로그인 화면 이동과 본인인증 로그인은 하나의 `로그인` 모듈에서 함께 처리됩니다.)

실행 폼에는 아래 입력이 있습니다.

- 브라우저 실행 모드
- 인증 수단
- 고객명
- 생년월일
- 성별
- 내외국인 구분
- 통신사
- 휴대폰 번호

**인증 수단**에 따라 본인인증 단계 동작이 다릅니다.

- **휴대폰인증**: SMS 요청 후 Run이 `WAITING_INPUT`으로 멈추면, Run 화면의 OTP 패널에서 인증번호를 제출해 재개합니다.
- **카카오인증**: OTP 입력 없이 자동화가 `인증요청` 후 약 60초 대기(카카오톡에서 인증)를 거친 뒤 `인증완료`를 누르고 로그인 완료를 기다립니다.
- **금융인증서인증 / 공동인증서인증**: 실행 폼에는 표시되지만 현재 API에서 실행을 거부합니다.

실행 폼에서 **성별·내외국인·통신사**는 휴대폰인증에서만 보이고, **고객명·생년월일·휴대폰 번호**는 휴대폰·카카오 모두에서 입력합니다.

현재 HOM 샘플의 보험금청구 관련 동작은 아래 전제를 따릅니다.

- 보험금청구 접수 단계(`charge05`)에서는 로컬 Desktop의 PNG 파일을 첨부합니다.
- 우선 `스크린샷*.PNG` / `Screenshot*.png` 패턴을 찾고, 없으면 Desktop의 다른 `PNG` 파일을 사용합니다.
- 보험금청구 결과 조회 단계는 **오늘 접수된 청구 중 청구내용이 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 인 진행중 건**을 찾아 상세 조회와 제출서류 확인까지 진행합니다.
- 이어지는 보험금청구 취소 단계는 동일한 진행중 건을 다시 찾아 접수 취소하고, 진행중 탭에서 사라지며 완료 탭에 취소 상태로 반영되는지 확인합니다.

### MHM 시스템

**MHM**(`대표홈페이지(모바일)`) Run은 HOM과 동일한 8개 모듈 순서(메인화면 접속 → 로그인(본인인증) → 계약목록 조회 → 계약상세 조회 → 보험금청구 접수 → 보험금청구 결과 조회 → 보험금청구 취소 → 장기보험증권 증명서 발급)로 실행되며, 모바일 웹(`m.hwgeneralins.com`)을 대상으로 합니다.

- 브라우저를 띄운 직후 **모바일 디바이스 모드를 먼저 적용**한 뒤 모바일 메인화면에 접속합니다. (PC 레이아웃으로 열리거나 리다이렉트되는 것을 막기 위함)
- 실행 폼 입력과 인증 수단 동작(휴대폰 OTP / 카카오 60초 대기)은 HOM과 동일합니다.
- 보험금청구 접수도 데스크탑 PNG 첨부, 청구내용 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 입력, 결과 조회·취소까지 HOM과 같은 전제를 따릅니다. (모바일 화면 UI에 맞춘 selector 사용)

각 화면별 상세 동작은 시나리오 문서를 참고하세요.

- HOM: `docs/scenarios/hom.md`
- MHM: `docs/scenarios/mhm.md`
- FP: `docs/scenarios/fp.md`
- HRP: `docs/scenarios/hrp.md`
- HWTC: `docs/scenarios/hwtc.md`
- CHBOT: `docs/scenarios/chbot.md`

## 결과 확인

테스트 실행 후 로그와 스크린샷은 로컬 프로젝트 폴더 아래 `artifacts/`에 저장됩니다.

추가로 아래 사항을 알아두면 됩니다.

- Run 화면의 상태, 실시간 로그, OTP 대기 정보는 메모리 기반이라 서버를 재시작하면 사라집니다. (OTP 대기는 **휴대폰인증** Run에서 본인인증 단계에 한합니다.)
- Suite 실행 상태·예약 정보도 메모리 기반이라 서버 재시작 시 사라집니다.
- 이미 생성된 아티팩트 파일은 로컬 `artifacts/` 폴더에 남아 있습니다.

## 주의 사항

- 이 프로젝트는 사내 내부용 도구입니다.
- 반드시 회사 정책과 허가된 테스트 환경에서만 사용해야 합니다.
- 테스트 대상 사이트 구조가 바뀌면 일부 자동화 동작이 실패할 수 있습니다.

## 선택 기능: 실패 원인 AI 분석

실패한 모듈에 대해 원인과 다음 조치를 자동 요약하는 선택 기능을 사용할 수 있습니다.

- 기본값은 비활성화이며, 설정하지 않으면 기존 실행 흐름은 그대로 유지됩니다.
- 현재 구현은 Gemini 계열 모델 호출을 전제로 하며, 실패 시에도 테스트 실행 자체는 계속 종료 처리됩니다.

이 기능은 아래 우선순위로 설정값을 읽습니다.

1. 터미널에서 직접 입력한 환경 변수
2. 프로젝트 폴더의 `.env` 파일

즉, 터미널에서 값을 입력하면 그 값을 먼저 사용하고, 터미널에 없으면 `.env` 파일 값을 사용합니다.

가장 쉬운 방법은 `.env.example` 파일을 복사해서 `.env` 파일을 만든 뒤 값을 채우는 것입니다.

```bash
cd e2eTester
cp .env.example .env
```

그다음 `.env` 파일을 열어서 아래 값을 실제 값으로 바꿉니다.

```bash
E2E_FAILURE_ANALYZER_ENABLED=true
GEMINI_API_KEY="실제_발급받은_API_KEY"
GEMINI_MODELS="gemini-3.1-flash-lite|gemini-2.5-flash|gemini-2.0-flash|gemini-flash-latest"
E2E_GEMINI_SSL_VERIFY=true
```

설정이 끝나면 아래처럼 바로 서버를 실행하면 됩니다.

```bash
cd e2eTester
python3 -m uvicorn app.main:app --reload
```

터미널에서 일회성으로 값을 덮어쓰고 싶다면 아래처럼 입력할 수 있습니다.

```bash
cd e2eTester

export E2E_FAILURE_ANALYZER_ENABLED=true
export GEMINI_API_KEY="실제_발급받은_API_KEY"
export GEMINI_MODELS="gemini-3.1-flash-lite|gemini-2.5-flash|gemini-2.0-flash|gemini-flash-latest"

python3 -m uvicorn app.main:app --reload
```

한 줄로 실행하고 싶다면 아래처럼 입력할 수도 있습니다.

```bash
cd e2eTester

E2E_FAILURE_ANALYZER_ENABLED=true \
GEMINI_API_KEY="실제_발급받은_API_KEY" \
GEMINI_MODELS="gemini-3.1-flash-lite|gemini-2.5-flash|gemini-2.0-flash|gemini-flash-latest" \
python3 -m uvicorn app.main:app --reload
```

브라우저에서 아래 주소로 접속하면 됩니다.

```text
http://127.0.0.1:8000
```

참고:

- `.env` 파일을 사용하면 터미널을 새로 열어도 다시 입력할 필요가 없습니다.
- `export`로 설정한 환경 변수는 해당 터미널 창을 닫으면 사라집니다.
- 터미널 환경 변수와 `.env` 파일에 같은 항목이 모두 있으면 터미널 환경 변수가 우선합니다.
- 회사망 프록시나 사설 인증서 때문에 Gemini API 에서 `CERTIFICATE_VERIFY_FAILED` 가 발생하면 `E2E_GEMINI_SSL_VERIFY=false` 로 SSL 인증서 검증을 우회할 수 있습니다.
- AI 분석 기능을 사용하지 않을 경우 기존처럼 `python3 -m uvicorn app.main:app --reload`만 실행하면 됩니다.
- 홈 화면에는 AI 분석 상태 카드가 표시되며, 현재 설정값이 유효한지 바로 확인할 수 있습니다.
- AI 분석 설정이 잘못되어도 앱은 실행되지만, 실패 분석 결과는 생성되지 않을 수 있습니다.

환경에 따라 `python3` 대신 회사 PC에 설치된 Python 실행 경로를 사용해야 할 수 있습니다.

예:

```bash
/usr/local/bin/python3 -m uvicorn app.main:app --reload
```

옵션 설명:

- `E2E_FAILURE_ANALYZER_ENABLED`: `true`일 때만 실패 분석 기능을 활성화합니다.
- `GEMINI_API_KEY`: Gemini API 호출 키입니다.
- `GEMINI_MODELS`: `|` 또는 `,`로 구분한 Gemini 모델 fallback 체인입니다. 비우면 기본 4모델 체인을 사용합니다.
- `E2E_GEMINI_SSL_VERIFY`: 기본값은 `true` 입니다. 회사망 SSL 검사 환경에서 Gemini API 인증서 검증 오류가 날 때만 `false` 로 바꿉니다.

## 선택 기능: 종료 메일 알림

테스트가 최종 종료되면 담당자에게 Gmail로 메일을 보낼 수 있습니다.

- 성공 종료(`PASSED`)와 실패 종료(`FAILED`) 모두 메일을 보냅니다.
- `WAITING_INPUT` 처럼 중간 대기 상태에서는 메일을 보내지 않습니다.
- 메일 본문 HTML은 항상 고정 디자인 템플릿(`report_renderer`)으로 결정적으로 렌더링하며, Gemini는 HTML이 아니라 분석 콘텐츠(핵심 요약·화면/로그 관찰·실패 분석)만 구조화 JSON으로 생성해 템플릿에 채웁니다. Gemini가 비활성이거나 호출에 실패하면 같은 템플릿이 AI 서술 없이(기본 문구로) 렌더링됩니다.
- 수신자 메일은 시스템(채널)별 환경 변수 `E2E_EMAIL_RECIPIENTS_{시스템코드}` 로 구분합니다. 기본 포함 시스템은 `HOM`·`MHM`·`FP`·`HRP`·`HWTC`·`CHBOT` 이며, 각각 `E2E_EMAIL_RECIPIENTS_HOM` 등으로 설정합니다.
- 한 채널에 여러 수신자를 넣고 싶다면 `|` 로 구분하면 됩니다.
- **전체 시스템 순차 점검(SUITE)** 이 종료되면, Suite에 포함된 각 시스템 Run의 수신자를 합쳐 **통합 결과 메일 1통**을 보냅니다. 개별 Run 종료 메일은 Suite 소속 Run에서는 보내지 않습니다.

예:

```bash
E2E_EMAIL_ENABLED=true
E2E_EMAIL_GMAIL_ACCOUNT="sender@gmail.com"
E2E_EMAIL_GMAIL_APP_PASSWORD="실제_앱비밀번호"
GEMINI_MODELS="gemini-3.1-flash-lite|gemini-2.5-flash|gemini-2.0-flash|gemini-flash-latest"
E2E_GEMINI_SSL_VERIFY=true
E2E_EMAIL_RECIPIENTS_HOM="user1@company.com|user2@company.com"
E2E_EMAIL_RECIPIENTS_MHM="user1@company.com|user2@company.com"
E2E_EMAIL_RECIPIENTS_FP="user1@company.com"
E2E_EMAIL_RECIPIENTS_HRP="user1@company.com"
E2E_EMAIL_RECIPIENTS_HWTC="user1@company.com"
E2E_EMAIL_RECIPIENTS_CHBOT="user1@company.com"
```

이 기능도 아래 우선순위로 값을 읽습니다.

1. 터미널에서 직접 입력한 환경 변수
2. 프로젝트 폴더의 `.env` 파일

즉, 터미널에 같은 항목을 넣으면 그 값이 우선이고, 없으면 `.env` 값을 사용합니다.

메일 동작 규칙:

- **개별 Run** 종료 메일:
  - 성공: 해당 Run 의 모든 스크린샷(`final.png`)을 첨부 대상으로 수집
  - 실패: 해당 Run 의 모든 스크린샷과 로그(`execution.log`)를 첨부 대상으로 수집
- **전체 점검(SUITE)** 종료 메일:
  - 선택되어 실행된 각 시스템 Run 결과를 하나의 보고서로 통합
  - `SKIPPED`(선택 제외) 시스템은 "제외"로 표시하고 통과 분모에는 포함하지 않음
  - 실패 Suite는 관련 시스템의 로그를 첨부 대상으로 우선 수집
- Gemini 분석 콘텐츠 생성 입력:
  - 성공/실패와 무관하게 해당 Run 의 모든 스크린샷과 실행 로그를 함께 전달
  - 각 스크린샷/로그에는 어느 모듈의 산출물인지 식별할 수 있는 레이블(모듈 ID, 모듈명, 순번)을 붙여 전달
- 메일 본문 HTML은 항상 고정 디자인 템플릿(`report_renderer`)으로 렌더링하고, Gemini 는 스크린샷과 로그를 분석한 콘텐츠(구조화 JSON)만 만들어 그 템플릿에 채움
  - 실행 개요, 핵심 요약, 모듈별 결과표, 화면 검증(스크린샷 분석), 로그 분석, 실패 상세 분석(실패 시), 첨부 안내 섹션으로 구성
- 첨부 용량이나 Gemini 입력 한도를 넘으면 가능한 만큼만 포함하고, 제외된 파일 목록을 메일 본문에 함께 표시

주의:

- 스크린샷과 로그에는 실제 테스트 데이터가 포함될 수 있으므로, 반드시 내부 담당자 메일 주소만 수신자로 사용해야 합니다.
- 첨부 파일과 일부 로그/스크린샷은 Gemini 분석 콘텐츠 생성을 위해 Gemini API로도 전달될 수 있습니다.
- 홈 화면에는 메일 알림 상태 카드가 표시되어 현재 설정이 유효한지 바로 확인할 수 있습니다.
- 회사망 SSL 검사로 Gemini API 인증서 오류가 나면 `E2E_GEMINI_SSL_VERIFY=false` 로 설정해 Gemini 호출의 SSL 검증만 우회할 수 있습니다.
