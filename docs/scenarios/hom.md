# HOM 시나리오 (대표홈페이지(PC))

이 문서는 `hom` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `hom`
- manifest: `app/systems/hom/manifest.yaml`
- 대상 사이트: `https://www.hwgeneralins.com` (고정값)
- 인증 수단: **휴대폰인증**(OTP pause/resume), **카카오인증**(60초 대기). 금융인증서·공동인증서는 UI placeholder 이며 API에서 실행을 거부한다.

## 2. 모듈 목록

`hom.yaml` `order` 기준:

1. `hom.main.access`
2. `hom.login` — 로그인 화면 이동(`app/systems/hom/steps/login_move.py`)과 본인인증 로그인을 한 단계(`login`)에서 처리한다. `auth_method`에 따라 `app/systems/hom/steps/phone_login.py`(휴대폰·OTP) 또는 `app/systems/hom/steps/kakao_login.py`(카카오·60초·`인증완료`) 실행
3. `hom.contract.list`
4. `hom.contract.detail`
5. `hom.compensation.charge` — `app/systems/hom/steps/compensation_charge.py` (`compensation_charge` 단계)
6. `hom.compensation.result` — `app/systems/hom/steps/compensation_result.py` (`compensation_result` 단계)
7. `hom.compensation.cancel` — `app/systems/hom/steps/compensation_cancel.py` (`compensation_cancel` 단계)
8. `hom.proof.long_term_policy` — `app/systems/hom/steps/long_term_policy_certificate.py` (`long_term_policy_certificate` 단계)

`app/systems/hom/steps/compensation_result.py`·`app/systems/hom/steps/compensation_cancel.py`는 결과 목록 진입·탭 선택·대상 행 탐색·상세(result02) 진입 등 공통 로직을 `app/systems/hom/steps/compensation_result_common.py`에서 공유한다.

모듈별 `timeout_seconds`: 로그인·보험금청구 접수·보험금청구 결과 조회·보험금청구 취소는 300초, 그 외 HOM 단계는 180초.

선택 실행을 위한 현재 의존성 그래프는 아래와 같다.

- `hom.main.access` → 없음
- `hom.login` → `hom.main.access`
- `hom.contract.list` → `hom.login`
- `hom.contract.detail` → `hom.contract.list`
- `hom.compensation.charge` → `hom.login`
- `hom.compensation.result` → `hom.compensation.charge`
- `hom.compensation.cancel` → `hom.compensation.charge`
- `hom.proof.long_term_policy` → `hom.login`

즉 HOM은 더 이상 단일 직선 체인만으로 해석하지 않는다. 로그인 이후 계약조회, 보험금청구, 증명서 발급이 서로 다른 브랜치로 분기하며, 대시보드에서 모듈을 선택 해제하면 선택되지 않은 모듈은 Run 화면에서 `SKIPPED` 로 표시된다.

## 3. 워크플로우

현재 실제 흐름은 아래와 같다.

```text
메인화면 접속
  -> 로그인 (로그인 이동 + 본인인증 로그인을 한 단계에서 처리)
      -> (휴대폰) OTP 대기/재개 또는 (카카오) 인증요청 → 60초 대기 → 인증완료 클릭
          -> 로그인 성공 후 팝업 정리
              -> 계약조회 브랜치: 계약목록 조회 -> 계약상세 조회
              -> 보상 브랜치: 보험금청구 접수(charge00~charge06) -> 보험금청구 결과 조회(result01 → result02 → pop-result04) -> 보험금청구 취소(result01 → result02 → 접수취소 → result01)
              -> 증명서 브랜치: 장기보험증권 증명서 발급
```

### Step 1. 메인화면 접속

파일:

- `app/systems/hom/steps/main_access.py`

역할:

- 메인 URL 직접 진입 (`page.goto`)
- 메인화면 전용 `20000ms` timeout 적용
- 랜딩 팝업 정리

### Step 2. 로그인

로그인 화면 이동과 본인인증 로그인을 하나의 `login` 단계에서 연속으로 수행한다. (휴대폰 OTP 대기로 Run이 일시정지되어도 SMS 요청은 한 번만 수행되도록 `phone_login_sms_requested` 플래그로 로그인 이동·SMS 요청을 함께 가드한다.)

파일:

- `app/systems/hom/steps/login_move.py` — 상단 로그인 링크 탐색·로그인 페이지 이동
- `app/systems/hom/steps/phone_login.py` — 휴대폰 인증 (SMS + OTP)
- `app/systems/hom/steps/kakao_login.py` — 카카오 인증 (OTP 없음, 인증요청 → 60초 대기 → 인증완료)
- `app/systems/hom/steps/login_common.py`
- `app/systems/hom/scripts/login_phone.py` — 개별 로그인 흐름 수동 실행용 CLI 진입 스크립트 (manifest 워크플로에서 직접 호출되지는 않음)

역할:

- 상단 로그인 링크를 탐색해 로그인 페이지로 이동
- 인증 수단에 따라 분기
- **휴대폰**: 휴대폰 인증 페이지 이동, 사용자·통신사 정보 입력, SMS 요청, OTP 제출
- **카카오**: [`/util/login/login.do`](https://www.hwgeneralins.com/util/login/login.do)에서 **「카카오 인증 로그인」** `listitem`의 **`link` 「로그인」**으로 첫 팝업 오픈 → 이름·생년월일·휴대폰 입력·동의 → **`인증요청`** → **60초 대기**(카카오톡에서 인증 진행) → **`인증완료`**
- `/my/main.do` 포함 URL 진입 확인
- 로그인 후 팝업 정리 시도
- 스크린샷 저장

### Step 3. 계약목록 조회

파일:

- `app/systems/hom/steps/contract_list.py`

역할:

- `MY한화 > 개인계약 조회` 이동
- `/fplaza/inquiry/contract01.do` 포함 URL 확인
- 목록 건수 확인
- 스크린샷 저장

### Step 4. 계약상세 조회

파일:

- `app/systems/hom/steps/contract_detail.py`

역할:

- `/fplaza/inquiry/contract01.do` 화면에서 증권번호 중 하나로 이동
- `/fplaza/inquiry/contract02.do` 포함 URL 확인
- 계약일반정보,수익자정보,자동이체현황,우편물 수령지/연락처,담당자정보,계약자정보 확인
- `final.png`: 실제 계약상세 웹 화면 전체 스크린샷(데이터 표시 검증용; `artifacts/`에 그대로 저장)

### Step 5. 보험금청구 접수

파일:

- `app/systems/hom/steps/compensation_charge.py`

역할:

- **진입**: GNB **`link` 「보상」** 호버 후 **`a[href*="/fplaza/compensation/charge00.do"]`** 가시 링크 클릭.
- `charge00`에서 **`a[href*="charge01.do"]`** 가시 링크로 `charge01` 이동(안내 화면의 보험금청구 신청 단계).
- `charge01`에서 **`get_by_role("link", name=/보험금청구\s*신청/)`** 가시 항목 클릭 → 레이어 **`보험금청구를 위한 필요서류는 확인하셨나요?`** 표시.
- 팝업에서 **`get_by_role("link", name=/준비가 된 상태/)`**(접근성 트리상 문구: *필요 서류를 확인하여 스캔 파일, 이미지 파일 등으로 준비가 된 상태입니다.*) 클릭 → `charge02` 로딩.
- `/fplaza/compensation/charge02.do` 포함 URL 확인
- 청구대상자 선택 표에서 본인 우측의 이름 클릭 후 하단 청구가능계약 조회 버튼 클릭
- 보험금청구 안내 팝업이 나오는 경우 확인 버튼 클릭하여 팝업 종료
- 신규접수 버튼을 클릭. 신규,추가접수 안내 팝업이 나오는 경우 신규접수 버튼 클릭.
- `/fplaza/compensation/charge03.do` 포함 URL 확인
- [필수]보험금 청구를 위한 요약 동의서 우측의 전체동의 버튼 클릭. 하단의 보험금청구신청 버튼 클릭
- `/fplaza/compensation/charge04.do` 포함 URL 확인
- 청구 상세내용 표에서 청구유형 우측의 라디오버튼 기타 클릭. 
- 청구 상세내용 표에서 사고일 우측의 캘린더를 클릭하여 현재 날짜 1달전의 날짜 선택.
- 하단 조회 버튼 클릭.
- 청구유형 선택 안내 팝업이 나오는 경우 확인 버튼 클릭.
- 상세내용 입력 표에서 청구내용 우측의 텍스트박스에 'IT직원 테스트입니다. 바로 취소할 예정입니다.' 입력
- 하단 다음 버튼 클릭.
- 청구내용 팝업이 나오는 경우 서류등록진행 버튼 클릭
- `/fplaza/compensation/charge05.do` 포함 URL 확인
- 서류제출 시 유의사항 팝업이 나오는 경우 우측 상단의 X 버튼 클릭.
- 진료비영수증, 진단서, 수술확인서 등 파일 첨부 영역의 파일 추가 버튼을 클릭한 뒤 데스크탑의 스크린샷*.PNG 이미지 중 하나를 랜덤 선택 업로드
- 진료비 세부(산정) 내역서 파일 첨부 영역의 파일 추가 버튼을 클릭한 뒤 데스크탑의 스크린샷*.PNG 이미지 중 하나를 랜덤 선택 업로드
- 하단 서류등록/청구완료 버튼 클릭
- 계속 진행하시겠습니까? 컨펌이 나오는 경우 확인 버튼 클릭.
- 정상적으로 등록되었습니다. 알럿이 나오는 경우 닫기 버튼 클릭
- `/fplaza/compensation/charge06.do` 포함 URL 확인

### Step 6. 보험금청구 결과 조회

파일:

- `app/systems/hom/steps/compensation_result.py`
- `app/systems/hom/steps/compensation_result_common.py` (결과 목록 진입·행 탐색·상세 진입 공통 헬퍼)

역할:

- **진입**: GNB **`link` 「보상」** 호버 후 **`a[href*="/fplaza/compensation/result01.do"]`** 가시 링크 클릭.
- `/fplaza/compensation/result01.do` 포함 URL 확인
- 결과 목록 상단 탭에서 진행중 탭 앵커 **`#ing`** 이 활성 상태인지 확인하고, 비활성 상태면 `#ing` 클릭.
- **`table` 「상해/질병/화재보험금 청구내역 목록」** 의 `tbody tr` 중 아래 조건을 모두 만족하는 행을 찾음:
- 접수일자 셀에 **오늘 날짜(`YYYY.MM.DD`)** 포함
- 청구내용 셀에 **`IT직원 테스트입니다. 바로 취소할`** 포함(목록에서는 말줄임표로 잘릴 수 있음)
- 진행상태 셀 값이 **`처리중`**
- 이용가능 서비스 셀에 **`제출서류확인`**, **`접수취소`** 버튼 노출
- 여러 건이면 목록 상단 첫 번째 행 선택
- 선택한 행의 접수번호 링크 클릭(목록 DOM 기준 `onclick="return goView(...)"`) → 상세 화면 이동
- `/fplaza/compensation/result02.do` 포함 URL 확인
- 상세 화면의 **`table` 「사고접수내용 상세」** 에서 아래 값 확인:
- 접수번호
- 보험청구일자 = 오늘 날짜
- 사고(진단)일자
- 청구유형
- 청구내용 = **`IT직원 테스트입니다. 바로 취소할 예정입니다.`**
- 상세 화면 서비스 버튼 확인:
- **`#btn3`** `제출서류확인` (`onclick="return previewDocu();"`)
- **`#btn4`** `접수취소` (`onclick="return cancelReceipt();"`)
- **`#btn3`** 제출서류확인 클릭 → 새 탭/팝업 **`/fplaza/compensation/pop-result04.do?conRcpNo={접수번호}`** 열림 확인
- 팝업에서 heading **`제출서류확인`** 확인
- 팝업의 제출 파일 목록에서 **최소 2건** 의 `등록파일` 항목과 각 파일의 등록일 표시, 이미지 파일 미리보기가 제대로 되는지 확인
- 각 `등록파일` 링크 클릭 시 파일 다운로드가 시작되는지 확인
- 팝업에서 **`전체 다운로드`** 버튼(`onclick="return zipDown();"`) 가시 확인

### Step 7. 보험금청구 취소

파일:

- `app/systems/hom/steps/compensation_cancel.py`
- `app/systems/hom/steps/compensation_result_common.py` (결과 목록 진입·행 탐색·상세 진입 공통 헬퍼)

역할:

- Step 6과 동일한 방식으로 result01에 다시 진입해 진행중 탭에서 동일 조건(오늘 날짜·`IT직원 테스트입니다. 바로 취소할`·`처리중`·`제출서류확인`/`접수취소` 버튼)의 행을 찾아 접수번호를 확보하고 상세 화면(`/fplaza/compensation/result02.do`)으로 이동
- 상세 화면 데이터가 확보한 접수번호로 채워질 때까지 대기
- 상세 화면에서 **`#btn4`** 접수취소 클릭
- 브라우저 `confirm` **`접수를 취소하시겠습니까?`** 표시 확인 후 확인
- 브라우저 `alert` **`정상적으로 처리 되었습니다.`** 표시 확인 후 확인
- `/fplaza/compensation/result01.do` 포함 URL로 복귀 확인
- 진행중 탭(**`#ing`**)에서 방금 취소한 접수번호가 더 이상 조회되지 않는지 확인
- 완료 탭 앵커 **`#fin`** 클릭
- 완료 탭 목록에서 동일 접수번호/청구내용 행 조회
- 해당 행의 진행상태 셀 값이 **`취소`** 인지 확인
- 완료 탭의 동일 행에서 이용가능 서비스가 **`제출서류확인`만 노출** 되는지 확인

### Step 8. 장기보험증권 증명서 발급

파일:

- `app/systems/hom/steps/long_term_policy_certificate.py`

역할:

- **진입**: GNB **「증명서 발급」** 호버 후 ** 장기보험증권 ** 가시 링크 클릭.
- 보험계약 선택 테이블에 항목이 존재하는지 확인. 존재한다면 가장 첫번째 선택 라디오버튼 클릭
- 발급방법선택 테이블의 다운로드 라디오버튼 클릭
- 화면 하단의 증명서발급 버튼 클릭. pdf 파일이 정상적으로 다운로드 되는지 확인.



## 4. UI 입력 모델

홈 화면의 `HOM` 실행 카드에는 아래 입력이 있다.

- 브라우저 실행 모드
- 인증 수단
- 고객명
- 생년월일
- 성별
- 내외국인 구분
- 통신사
- 휴대폰 번호

조건부 규칙:

- 성별·내외국인·통신사는 **휴대폰인증**에서만 폼에 노출 (`show_when`)
- 고객명·생년월일·휴대폰 번호는 **휴대폰인증·카카오인증**에서 노출 (`manifest`의 `show_when.auth_method`에 `phone`·`kakao` 나열)
- 금융인증서·공동인증서는 UI placeholder이며 API에서 실행을 거부

추가 선택 규칙:

- 실행 전 그래프에서 8개 모듈의 실행 여부를 개별 선택할 수 있다.
- 기본값은 8개 전체 선택이다.
- 선택 해제된 모듈은 실행 요청 payload의 `selected_module_ids` 에 포함되지 않으며 Run 화면에서 `SKIPPED` 로 렌더링된다.
- 선행 모듈이 빠진 잘못된 조합은 UI에서 경고를 보여줄 수 있지만 최종 판정은 서버가 수행하며, 실행 생성 시 400 오류로 거부된다.
