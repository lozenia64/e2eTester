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

1. 홈 화면에서 테스트할 시스템을 선택합니다.
2. 필요한 입력값을 작성합니다.
3. `실행` 버튼을 눌러 테스트를 시작합니다.
4. Run 화면에서 진행 상태, 로그, 결과를 확인합니다.
5. 추가 입력이 필요한 경우 화면 안내에 따라 계속 진행합니다.

### HOM 샘플 시스템

현재 기본으로 포함된 **HOM**(한화손해보험 샘플) Run은 다음 순서로 모듈이 실행됩니다.

1. 메인화면 접속 → 로그인 이동 → 본인인증 로그인 → 계약목록 조회 → 계약상세 조회 → 보험금청구 접수(charge06까지) → 보험금청구 결과 조회 및 취소

실행 폼에는 아래 입력이 있습니다.

- 브라우저 실행 모드
- Base URL
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
- 보험금청구 결과 조회 및 취소 단계는 **오늘 접수된 청구 중 청구내용이 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 인 진행중 건**을 찾아 상세 조회, 제출서류 확인, 접수 취소까지 진행합니다.

## 결과 확인

테스트 실행 후 로그와 스크린샷은 로컬 프로젝트 폴더 아래 `artifacts/`에 저장됩니다.

추가로 아래 사항을 알아두면 됩니다.

- Run 화면의 상태, 실시간 로그, OTP 대기 정보는 메모리 기반이라 서버를 재시작하면 사라집니다. (OTP 대기는 **휴대폰인증** Run에서 본인인증 단계에 한합니다.)
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
GEMINI_MODEL="gemini-3.1-flash-lite"
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
export GEMINI_MODEL="gemini-3.1-flash-lite"

python3 -m uvicorn app.main:app --reload
```

한 줄로 실행하고 싶다면 아래처럼 입력할 수도 있습니다.

```bash
cd e2eTester

E2E_FAILURE_ANALYZER_ENABLED=true \
GEMINI_API_KEY="실제_발급받은_API_KEY" \
GEMINI_MODEL="gemini-3.1-flash-lite" \
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
- `GEMINI_MODEL`: 사용할 모델 이름입니다. 비우면 기본 모델 값을 사용합니다.
