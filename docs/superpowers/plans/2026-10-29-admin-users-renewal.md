# 관리자 사용자 관리 리뉴얼 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 승인된 사용자 목록 + 권한 상세 목업을 실제 사용자 API에 연결한다.
**Architecture:** Jinja는 접근 가능한 마크업, 전용 Vite 엔트리는 CSS와 화면 컨트롤러를 연결한다. 렌더링과 API/상태 제어를 분리하며 API 정책은 유지한다.
**Tech Stack:** Jinja, TypeScript, CSS 토큰, Vitest/jsdom.
**Spec:** `docs/superpowers/specs/2026-10-29-admin-users-renewal-design.md`

## Global Constraints

현재 사용자 지정 `관리자-화면-리뉴얼` 브랜치에서 수행. 한국어 UI, 기존 토큰 재사용, 파일당 400줄 이내. 사용자 승인 범위는 구현이며 커밋·PR·푸시는 별도 요청 전 수행하지 않는다.

## Review Focus

- 일반 사용자 빈 권한은 접근 없음이며 전체 선택은 등록된 코드를 전송한다.
- 사용자 선택 변경과 요청 중 조작으로 다른 사용자의 권한을 덮어쓰지 않는다.
- 일부 조회 실패·저장 실패 시 오류와 재시도, 기존 초안을 유지한다.
- 미등록 코드·HTML 문자를 포함하는 이름을 안전하게 표시한다.
- 모바일·키보드에서 상세와 모달에 접근하고 포커스를 복귀한다.

## 작업 1: 화면과 API 연결

- [x] `app/web/frontend/admin-users/controller.test.ts`에 검색/필터·권한 빈 목록·전체 저장·미저장 전환·실패·추가/활성/삭제·XSS 테스트를 먼저 작성하고 실패를 확인한다.
- [x] `app/web/templates/admin/users.html` 교체, `admin-users/{types,render,controller}.ts`, `styles.css`, `entries/admin-users.ts` 생성, `vite.config.ts` 등록. 기존 관리 셸을 유지한다.
- [x] 대상 Vitest, 타입 검사, lint, 프론트 게이트와 문서 검사를 실행한다.

## 작업 2: 화면 검증과 리뷰

- [x] `docs/specs/identity/03-user-admin.md`에 동작·AC를 동기화하고 Vite 빌드를 실행한다.
- [x] Orca에서 실제 `/admin/users` 읽기 전용 화면·검색·필터·권한 초안 변경/취소를 확인하고 모바일 가로 넘침을 검사한다.
- [x] 별도 리뷰 에이전트가 작업 diff를 검토하고 중요한 문제를 수정·재검증한다.

## 실행 기록

- Ruling: 승인된 현재 브랜치에서 직접 구현 — 사용자가 현재 브랜치로 작업을 이어가고 있어 새 워크트리는 만들지 않는다.
- Ruling: 목업의 빈 권한=전체 안내 대신 실제 정책에 맞춘다 — 빈 코드는 접근 없음이며 API 정책을 변경하지 않는다.

- 구현 완료: 전용 엔트리·컨트롤러·렌더러·토큰 CSS로 분리하고 기존 API를 유지했다.
- Review: 독립 리뷰에서 전체 선택 시 해제한 미등록 코드가 복원되는 문제를 발견했다. 회귀 테스트의 실패를 확인한 뒤 현재 초안의 미등록 코드만 보존하도록 수정했다. 추가 성공 후 포커스 복귀도 실패 테스트 후 수정했다. 미해결 Important/Critical 및 유보한 Minor 없음.
- 검증: Vitest 33개 파일/221개 테스트, 사용자 관리 동작 16개 포함. `tests/frontend` 147개, TypeScript, ESLint, FG-001~007, 문서 정합성, diff 공백 검사 통과.
- 브라우저: Orca 실제 `/admin/users` 조회·검색·상태 필터·권한 초안 원복·추가 모달 열기/닫기·포커스 복귀·콘솔 오류 없음 확인. 390px/1402px 가로 넘침 없음. 실제 계정 변경 요청은 하지 않았다.
- 운영: 이전 설정을 유지하던 같은 저장소의 Vite watch 2개를 중지하고 최신 설정의 감시 빌드 1개로 복구했다. 앱 서버와 사용자 브라우저는 재시작하지 않았다.
- 기존 Run 지도 테스트의 색 fixture를 RGB 수치에서 생성하도록 수정해 FG-002 위반도 해소했다. 제품의 지도 동작은 변경하지 않았다.
- 사용자 요청에 따라 현재 브랜치에 구현·테스트·설계 문서를 커밋한다. 목업과 화면 캡처는 로컬 참고 자료로 유지한다.
