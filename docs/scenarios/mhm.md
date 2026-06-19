# MHM 시나리오 (모바일 대표홈페이지)

이 문서는 `mhm` 시스템의 E2E 테스트 시나리오를 설명한다.

플랫폼 공통 아키텍처(계층 구조, 상태 전이, 이벤트 모델, 아티팩트 전략)는 [E2E_ARCHITECTURE.md](../../E2E_ARCHITECTURE.md)를 참고한다.

## 1. 시스템 개요

- 시스템 코드: `mhm`
- manifest: `app/systems/mhm/manifest.yaml`
- 대상 사이트: `https://m.hwgeneralins.com` (고정값)
- **브라우저 기동 순서(필수)**: Playwright로 Chrome을 연 뒤 **모바일 디바이스 모드를 먼저 적용**하고, 그 다음에 `m.hwgeneralins.com`에 접속한다. 모바일 모드 적용 전에 접속하면 PC 레이아웃으로 열리거나 리다이렉트될 수 있다. 구현은 `app/systems/mhm/steps/login_common.py` 의 `apply_mobile_device_mode()`(executor `build_runtime()` 단계) → `app/systems/mhm/steps/main_access.py` 의 `run()` 순서를 따른다.
- 인증 수단: **휴대폰인증**(OTP pause/resume), **카카오인증**(30초 대기·최대 3회 재시도). 금융인증서·공동인증서는 UI placeholder 이며 API에서 실행을 거부한다.
- **전체 순차 점검(SUITE)**: 홈 SUITE 카드에서 시스템 체크박스로 포함 여부를 선택할 수 있다. SUITE에 포함되면 이 시스템의 **전체 모듈**이 순차 실행되며, 인증 정보는 SUITE 카드의 MHM 전용 패널에서 설정한다.

## 2. 모듈 목록

`mhm.yaml` `order` 기준:

1. `mhm.main.access`
2. `mhm.login` — 로그인 화면 이동(`app/systems/mhm/steps/login_move.py`)과 본인인증 로그인을 한 단계(`login`)에서 처리한다. `auth_method`에 따라 `app/systems/mhm/steps/phone_login.py`(휴대폰·OTP) 또는 `app/systems/mhm/steps/kakao_login.py`(카카오·30초·`인증확인`·최대 3회 재시도) 실행
3. `mhm.contract.list`
4. `mhm.contract.detail`
5. `mhm.compensation.charge` — `app/systems/mhm/steps/compensation_charge.py` (`compensation_charge` 단계)
6. `mhm.compensation.result` — `app/systems/mhm/steps/compensation_result.py` (`compensation_result` 단계)
7. `mhm.compensation.cancel` — `app/systems/mhm/steps/compensation_cancel.py` (`compensation_cancel` 단계)
8. `mhm.proof.long_term_policy` — `app/systems/mhm/steps/long_term_policy_certificate.py` (`long_term_policy_certificate` 단계)

`app/systems/mhm/steps/compensation_result.py`·`app/systems/mhm/steps/compensation_cancel.py`는 결과 목록 진입·탭 선택·대상 행 탐색·상세(result02) 진입 등 공통 로직을 `app/systems/mhm/steps/compensation_result_common.py`에서 공유한다.

모듈별 `timeout_seconds`: 로그인·보험금청구 접수·보험금청구 결과 조회·보험금청구 취소는 300초, 그 외 MHM 단계는 180초.

선택 실행을 위한 현재 의존성 그래프는 아래와 같다.

- `mhm.main.access` → 없음
- `mhm.login` → `mhm.main.access`
- `mhm.contract.list` → `mhm.login`
- `mhm.contract.detail` → `mhm.contract.list`
- `mhm.compensation.charge` → `mhm.login`
- `mhm.compensation.result` → `mhm.compensation.charge`
- `mhm.compensation.cancel` → `mhm.compensation.charge`
- `mhm.proof.long_term_policy` → `mhm.login`

즉 MHM은 더 이상 단일 직선 체인만으로 해석하지 않는다. 로그인 이후 계약조회, 보험금청구, 증명서 발급이 서로 다른 브랜치로 분기하며, 대시보드에서 모듈을 선택 해제하면 선택되지 않은 모듈은 Run 화면에서 `SKIPPED` 로 표시된다.

## 3. 워크플로우

현재 실제 흐름은 아래와 같다.

```text
메인화면 접속
  -> 로그인 (로그인 이동 + 본인인증 로그인을 한 단계에서 처리)
      -> (휴대폰) OTP 대기/재개 또는 (카카오) 인증요청 → 30초 대기 → 인증확인 클릭 (미완료 시 인증요청 재시도, 최대 3회)
          -> 로그인 성공 후 팝업 정리
              -> 계약조회 브랜치: 계약목록 조회 -> 계약상세 조회
              -> 보상 브랜치: 보험금청구 접수(IbnfDmRcp1020~1090) -> 보험금청구 결과 조회(IbnfDmRstInq1000~1020) -> 보험금청구 취소(IbnfDmRstInq1010~1020, UI 알림 확인)
              -> 증명서 브랜치: 장기보험증권 증명서 발급
```

### Step 1. 메인화면 접속

파일:

- `app/systems/mhm/steps/main_access.py`

역할:

- **선행 조건**: 공용 `RepHomepageExecutor.build_runtime()` 가 모바일 채널 프로파일(`MOBILE_CHANNEL`, `mobile=True`)로 브라우저 기동 후 `app/systems/mhm/steps/login_common.py` 의 `apply_mobile_device_mode()` 로 모바일 모드 적용 완료
- 모바일 모드 적용 확인(`ensure_mobile_mode_before_navigation`) 후 메인 URL 직접 진입 (`page.goto`)
- 메인화면 전용 `20000ms` timeout 적용
- 랜딩 팝업 정리

### Step 2. 로그인

로그인 화면 이동과 본인인증 로그인을 하나의 `login` 단계에서 연속으로 수행한다. (휴대폰 OTP 대기로 Run이 일시정지되어도 SMS 요청은 한 번만 수행되도록 `phone_login_sms_requested` 플래그로 로그인 이동·SMS 요청을 함께 가드한다.)

파일:

- `app/systems/mhm/steps/login_move.py` — 모바일 로그인 진입(햄버거/하단 메뉴 등)·로그인 페이지 이동
- `app/systems/mhm/steps/phone_login.py` — 휴대폰 인증 (SMS + OTP)
- `app/systems/mhm/steps/kakao_login.py` — 카카오 인증 (OTP 없음, 인증요청 → 30초 대기 → 인증확인, 미완료 시 최대 3회 재시도)
- `app/systems/mhm/steps/login_common.py`
- MHM은 현재 별도 수동 로그인 CLI 진입 스크립트를 두지 않는다.

역할:

- 모바일 로그인 진입(햄버거/하단 메뉴 등)으로 로그인 페이지로 이동
- 인증 수단에 따라 분기
- **휴대폰**: [`/lin/fid/LginTypSlc1000`](https://m.hwgeneralins.com/lin/fid/LginTypSlc1000)에서 **`다른 로그인 방법`**(`main button.btn.btn_more`) 클릭 → **`휴대폰인증`**(`main a[role="button"].c5` / `span.cert_select_text`) 클릭 → [`/lin/fid/LginTypSlc1020`](https://m.hwgeneralins.com/lin/fid/LginTypSlc1020) 폼에서 `#customerName`·`#jumin1`(YYMMDD)·`#jumin2`(성별/내외국인)·`#cellphone0`(통신사)·`#cellphone1`(휴대전화번호) 입력·**`#checkAll` 전체동의** → **`인증요청`**(`button.btn.s3.c4`) → **`.dialog.modal.alert.show` 알림(인증번호가 발송되었습니다.)** 의 **`확인`**(`button.btn.ui_dialog_close`) 클릭 → OTP를 `#reqPhoneCheck`에 입력 후 **`확인`**(`button.btn.s1.c1`, 활성화 후 클릭) → [`/myh/mai/MySubMain1000`](https://m.hwgeneralins.com/myh/mai/MySubMain1000) 리다이렉트 → (있으면) **`#coachMarkDialog` 코치마크** 단계별 클릭으로 닫기 → (있으면) **모바일 안내장 신청안내** 팝업에서 **`다음에 할게요`**(`button.btn.s1.c2`) 클릭
- **카카오**: [`/lin/fid/LginTypSlc1000`](https://m.hwgeneralins.com/lin/fid/LginTypSlc1000)에서 **`카카오인증`** 버튼 클릭 → [`/lin/kct/KakaoWebLgin1000`](https://m.hwgeneralins.com/lin/kct/KakaoWebLgin1000) 본인인증 페이지에서 이름·생년월일·휴대전화번호 입력·**전체동의** → **`인증요청`** → 발송 알림 **`확인`** 닫기 → **30초 대기**(카카오톡에서 인증 진행) → **`인증확인`** 클릭 → (「인증이 완료되지 않았습니다」 등 미완료 알림 시 **`인증요청` 재시도**, 최대 3회, 3회 모두 실패 시 로그인 실패)
- [`/myh/mai/MySubMain1000`](https://m.hwgeneralins.com/myh/mai/MySubMain1000) 포함 URL 진입 확인
- 로그인 후 팝업 정리 시도
- 스크린샷 저장

### Step 3. 계약목록 조회

파일:

- `app/systems/mhm/steps/contract_list.py`

역할:

- 로그인 후 팝업 정리(`maybe_close_post_login_popup`)
- [`/myh/mai/MySubMain1000`](https://m.hwgeneralins.com/myh/mai/MySubMain1000) 메인화면에서 **`계약현황조회`**(`main button.btn.s3.c4`) 클릭 (없으면 전체메뉴 → **개인계약 조회**, 최종 fallback `/myh/ciq/PsnCrInq1010` 직접 진입)
- `/myh/ciq/PsnCrInq1010` 포함 URL 및 **보험계약 조회** 화면 확인
- **총 N 건** 또는 계약 카드(`main a[role="button"]:has(h3)`) 건수 확인
- 스크린샷 저장

### Step 4. 계약상세 조회

파일:

- `app/systems/mhm/steps/contract_detail.py`

역할:

- `/myh/ciq/PsnCrInq1010` 목록 화면에서 첫 번째 계약 카드(`main button:has(h3)`) 클릭
- `/myh/ciq/PsnCrInq1020`·`PsnCrInq1040` 등 상세 URL(`/myh/ciq/PsnCrInq`, 목록 `1010` 제외) 확인
- 증권번호(`FA`/`LA` + 숫자) 및 **계약자정보**, **담당자정보**, **납입정보** 섹션 확인
- `final.png`: 실제 계약상세 웹 화면 전체 스크린샷(데이터 표시 검증용; `artifacts/`에 그대로 저장)

### Step 5. 보험금청구 접수

파일:

- `app/systems/mhm/steps/compensation_charge.py`

역할:

- **진입**: 우측 상단 **`전체메뉴 열기`** → 탭 **`보상`** → **질병/상해보험** 하위 **`보험금청구 접수`** (`nav` 내 첫 번째 `보험금청구 접수` 항목) 클릭 → [`/cmp/dii/IbnfDmRcp1020`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1020) 안내 화면.
- 안내 화면에서 **`보험금청구하기`** 버튼 클릭 → [`/cmp/dii/IbnfDmRcp1040`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1040) 청구 대상 선택.
- (있으면) **실손24 알림** 팝업 — 진입 직후·**`보험금청구하기`** 클릭 후·**`본인`** 선택 전에 **`오늘 더 이상 안 볼래요`** 또는 **`팝업창 닫기`** 로 닫기.
- **`본인`** 선택, **`아니오, 없어요(신규접수)`** 선택, **`다음`** 클릭.
- (있으면) 신규접수·**동일한 사고로 청구하신 이력** 등 안내 팝업 **`확인`** 클릭.
- [`/cmp/dii/IbnfDmRcp1050`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1050) 1단계(청구사유): **`#dateInput`** 에 발병(사고)일 **1개월 전**(`YYYY.MM.DD`) 입력, 사고 유형 **`기타`**(`label:has(em.sel_lb_tit:text-is("기타"))`, 라디오 input 직접 클릭 대신 label **`force`** 클릭·화면 중앙 스크롤) 선택, 하단 고정 **`청구사유 입력완료(1/3)`** 버튼 활성화 후 클릭.
- (있으면) **동일한 발병(사고)일/사고유형** 기존 청구 이력 안내 팝업(`.dialog.modal.alert.show`) **`아니오`** 클릭 — 동의 안내·요약 동의서 화면 위에 떠도 **`force`** 클릭으로 먼저 닫기. 1050에서 뜬 경우 **`청구사유 입력완료(1/3)`** 재클릭.
- (있으면) 사고유형 확인 팝업 **`확인했어요`** 클릭.
- (있으면) 동의 안내 팝업 **`label[for="[필수] 전체동의"]`** → 요약 동의서 시트 하단까지 스크롤 후 **`전체동의`** → 동의 안내 **`다음`** 클릭(모달 내부 **`scrollIntoView` + DOM 클릭**).
- [`/cmp/dii/IbnfDmRcp1052`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1052) 2단계(상세정보): 청구 유형 **`진단비`**, 청구 상세 유형 **`기타 진단`**(`label` **`force`** 클릭), **`#cont`** 에 `IT직원 테스트입니다. 바로 취소할 예정입니다.` 입력.
- **`#acccombo`** → **`계좌선택`**, (미선택 시) bottom sheet에서 저장 계좌 선택, 의료급여 수급권자 **`label[for="radio10"]` 해당없음**(`force` 클릭), 하단 **`상세정보 입력완료(2/3)`** 활성화 후 클릭.
- 접수정보 확인 시트 **`확인 후 서류제출 하러 가기`** 클릭.
- [`/cmp/dii/IbnfDmRcp1070`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1070) 3단계(서류등록): **`보험금청구서류 (영수증 등 증빙자료)`** · **`진료비 세부(산정)내역서`** 각각 **`label[for="galleyFile"]`**(앨범)으로 데스크탑 `스크린샷*.PNG` 랜덤 업로드.
- **`서류 제출 후 완료(3/3)`** 클릭 → (있으면) **`총 N건의 첨부파일을 전송합니다`** 팝업 **`서류제출`** 클릭.
- [`/cmp/dii/IbnfDmRcp1090`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRcp1090) 완료 화면(제목 **보험금청구를 완료했어요**) 확인.
- (있으면) **서비스만족도 조사** 팝업(`.dialog.full.show`) 우측 상단 **`button.dialog_close.ui_dialog_close`**(팝업창 닫기) 클릭.

### Step 6. 보험금청구 결과 조회

파일:

- `app/systems/mhm/steps/compensation_result.py`
- `app/systems/mhm/steps/compensation_result_common.py` (결과 목록 진입·카드 탐색·상세 진입 공통 헬퍼)

역할:

- **진입**: **`전체메뉴 열기`** → 탭 **`보상`** → **질병/상해보험** 하위 **`보험금청구 결과 조회`** (`#code03020300`) 클릭.
- [`/cmp/dii/IbnfDmRstInq1000`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1000) 안내 화면에서 **`조회하기`** 클릭 → [`/cmp/dii/IbnfDmRstInq1010`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1010) 목록.
- 목록 기본 필터 **`진행중 본인`**(`main button.icon_filter`) 상태에서 **`main a:has(h3)`** 청구 카드 중 아래 조건을 모두 만족하는 카드 선택:
  - **접수일**에 **오늘 날짜(`YYYY.MM.DD`)** 포함
  - 제목(`h3`)에 **`IT직원 테스트입니다. 바로 취소할`** 포함
  - **`서류추가`** 또는 **`진행중`** 등 진행 중 상태 힌트 포함
- 선택한 카드 클릭 → [`/cmp/dii/IbnfDmRstInq1020`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1020) 상세.
- **보험금청구 내용** 섹션에서 아래 값 확인:
  - **접수번호** (예: `26061403283`, `/청구순번:` 접미사 제거 후 비교)
  - **보험금청구일자** = 오늘 날짜
  - **발병(사고)일**
  - **청구 유형** (예: `기타비용`)
  - **청구 내용** = **`IT직원 테스트입니다. 바로 취소할 예정입니다.`**
- 상세 버튼 확인: **`제출서류 확인하기`**, **`접수취소`**
- **`제출서류 확인하기`** 클릭 → **제출 서류 확인** 전체 시트(`.dialog.full.show`)에서 **슬라이드 총 건수**는 `.swiper-pagination-total`(또는 `.hgismt_paper_swipe .list_total`의 `총 N건`) 기준 **2건 이상** 확인
- 슬라이드는 **1장씩** 표시되므로, 각 슬라이드마다 활성 `.swiper-slide-active`의 **미리보기 `img`** 가 `naturalWidth > 0` 로딩될 때까지 대기(최대 30초)한 뒤 **`button.hgismt_next`** 로 다음 서류로 넘기며 전건 검증
- 검증 완료 후 **`확인`** 으로 닫기

### Step 7. 보험금청구 취소

파일:

- `app/systems/mhm/steps/compensation_cancel.py`
- `app/systems/mhm/steps/compensation_result_common.py` (결과 목록 진입·카드 탐색·상세 진입·필터 전환 공통 헬퍼)

역할:

- Step 6과 동일한 방식으로 [`/cmp/dii/IbnfDmRstInq1010`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1010) 목록에 진입해 **`진행중 본인`** 필터에서 동일 조건(오늘 날짜·`IT직원 테스트입니다. 바로 취소할`·진행 중 상태 힌트)의 카드를 찾아 접수번호를 확보하고 [`/cmp/dii/IbnfDmRstInq1020`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1020) 상세로 이동
- 상세 화면 데이터가 확보한 접수번호로 채워질 때까지 대기
- 상세 화면에서 **`접수취소`**(`main button:has-text("접수취소")`) 클릭
- UI 알림 **`접수를 취소하시겠습니까?`** 표시 확인 후 **`.dialog.modal.alert.show`** 내부 **`예`**(`exact=True`) 클릭
- UI 알림 **`정상 처리 되었습니다.`** 표시 확인 후 동일 알림 다이얼로그 내부 **`확인`**(`exact=True`, 상세 화면 **`제출서류 확인하기`** 링크와 구분) 클릭
- [`/cmp/dii/IbnfDmRstInq1010`](https://m.hwgeneralins.com/cmp/dii/IbnfDmRstInq1010) 목록으로 복귀 확인
- **`진행중`** 필터(`main button.icon_filter` → **조회 조건 설정** → **진행중** → **확인**)에서 방금 취소한 접수번호가 더 이상 조회되지 않는지 확인 (빈 목록 문구 **`진행 중인 보험금청구 내역이 없습니다.`** 포함)
- **`완료`** 필터로 전환 후 동일 접수번호/청구내용 카드 조회
- 해당 카드에 **`취소`** 상태 태그(`span.tag.c3`)가 포함되는지 확인
- 취소된 카드 상세에서 **`보험금청구 접수가 취소되었습니다`** 제목 확인, **`접수취소`** 버튼은 노출되지 않고 **`제출서류 확인하기`**·**`동일내용 다시청구`** 는 노출되는지 확인

### Step 8. 장기보험증권 증명서 발급

파일:

- `app/systems/mhm/steps/long_term_policy_certificate.py`

역할:

- **진입**: **`전체메뉴 열기`**(`#btnGnb`) → `#gnb` 내부 **`.nav_area` / `.menu_area` 스크롤** 후 탭 **`증명서발급`**(`id="05000000"`, CSS `[id="05000000"]`) → **`증명서발급`**(`#code05010000`) 클릭(일반 클릭 실패 시 JS/`force` 폴백) → **필요한 증명서를 선택하세요** 화면 진입
- **공통** 섹션 **`보험증권(장기/자동차)`** 클릭 → **보험증권(장기/자동차)을 발급하실 수 있습니다** 화면(`#ltins` 장기 탭) 진입
- **`계약 선택`**(`.certificate_list a.btn`) 클릭 → **계약 선택** 전체 시트(`.dialog.full.show`)에서 첫 계약(`.list.box a.btn.inner`) 선택 후 하단 **`확인`**(`exact=True`) 클릭
- **발급방법 선택**에서 **`다운로드`**(`#issueMtdDownload`) 탭 선택
- 하단 **`증명서 발급`**(`.fixed_bottom_button button.btn.s1.c1`, 활성화 후) 클릭 → PDF 다운로드 및 **`PDF 파일 다운로드가 완료되었습니다.`** 알림 확인 후 **`확인`** 으로 닫기



## 4. UI 입력 모델

홈 화면의 `MHM` 실행 카드에는 아래 입력이 있다.

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
