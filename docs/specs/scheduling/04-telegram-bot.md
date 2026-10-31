# SPEC-SCHED-004: 텔레그램 봇 예약 즉시 실행

| 항목 | 값 |
| --- | --- |
| **ID** | `SPEC-SCHED-004` |
| **상태** | `approved` |
| **의존** | `SPEC-SCHED-003` |
| **구현** | `app/contexts/scheduling/telegram_bot.py` |

## 1. 개요

소유자 1인이 텔레그램 봇으로 저장된 예약을 즉시 실행한다. API 프로세스가 `getUpdates` long polling 으로 수신하고 `trigger_now` 를 내부 호출한다. 공개 인바운드 경로는 없다. 설정: [docs/telegram_bot.md](../../telegram_bot.md).

## 2. FR-001: 활성화

`E2E_TELEGRAM_BOT_TOKEN` 과 `E2E_TELEGRAM_OWNER_ID` 가 모두 있을 때만 켠다.

## 3. FR-002: 인가

비공개 채팅이면서 `from.id == chat.id == owner` 일 때만 처리한다. 그 외 발신자에게는 답하지 않는다. `allowed_updates` 는 `message`, `callback_query` 로 고정한다.

## 4. FR-003: 실행 흐름

`/run` → 예약 선택 → 확인 카드 [실행]. 목록과 카드는 부수효과가 없다.

- 확인 nonce 는 메모리에 1개만 두고 첫 await 전에 소비한다.
- 유효 시간은 카드 발급 후 1~60초이고 벽시계로 잰다.
- 2분 넘게 지난 메시지는 처리하지 않고 알린다.

## 5. FR-004: 진행·OTP

- 진행은 메시지 하나를 문구가 바뀔 때만 편집한다. 결과와 OTP 요청은 새 메시지로 보낸다.
- OTP 는 요청 메시지에 대한 답장만 받고, 처리 뒤 답장을 삭제한다.
- 대기가 풀리면 OTP 요청 메시지를 삭제한다.

## 6. FR-005: 채팅 노출 금지

`trigger_token`, 입력값, 예외 상세, 사이트 OTP 안내 문구, 스크린샷은 보내지 않는다. 봇 토큰이 든 URL 은 예외와 로그에 남기지 않는다.

## 7. 수용 기준

### AC-001: 지연 탭 차단

```gherkin
Given 확인 카드가 60초 넘게 지남
When [실행] 탭이 도착
Then 실행하지 않고 만료를 알린다
```

### AC-002: 재전달 탭 1회 실행

```gherkin
Given 유효한 확인 카드
When 같은 [실행] 탭이 두 번 도착
Then trigger_now 는 한 번만 호출된다
```

### AC-003: 재시작 전 탭 차단

```gherkin
Given 앱 재시작으로 nonce 가 사라짐
When 이전 카드의 [실행] 탭이 도착
Then 실행하지 않는다
```

### AC-004: 미인가 차단

```gherkin
Given 소유자가 아닌 발신자
When /run 또는 [실행] 탭을 보냄
Then 답하지 않고 실행하지 않는다
```

## 8. 한계

- PC 절전 중에는 실행도 응답도 불가하다.
- 폴러는 프로세스당 하나이므로 uvicorn 다중 워커나 같은 토큰의 다중 PC 구성을 지원하지 않는다.
