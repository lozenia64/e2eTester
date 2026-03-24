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

## 결과 확인

테스트 실행 후 로그와 스크린샷은 로컬 프로젝트 폴더 아래 `artifacts/`에 저장됩니다.

## 주의 사항

- 이 프로젝트는 사내 내부용 도구입니다.
- 반드시 회사 정책과 허가된 테스트 환경에서만 사용해야 합니다.
- 테스트 대상 사이트 구조가 바뀌면 일부 자동화 동작이 실패할 수 있습니다.
