# 관리자 모듈 설정 리뉴얼 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 승인된 시스템 탐색 + 모듈 편집 목업을 기존 설정 API에 연결한다.
**Architecture:** Jinja는 접근 가능한 마크업을 제공한다. `admin-modules` 타입/상태 함수, 렌더러, 컨트롤러, 토큰 CSS를 전용 Vite 엔트리로 연결한다.
**Tech Stack:** Jinja, TypeScript, CSS, Vitest/jsdom.
**Spec:** `docs/superpowers/specs/2026-10-29-admin-modules-renewal-design.md`

## Global Constraints

현재 사용자 지정 `관리자-화면-리뉴얼` 브랜치에서 진행한다. 한국어 UI, 기존 디자인 토큰, 파일당 400줄 이하. API·백엔드 정책은 유지하며 커밋·PR은 요청 전 수행하지 않는다.

## Review Focus

- 부분 성공은 저장된 모듈만 기준값을 갱신하고 실패 초안은 남긴다.
- 필터/다른 페이지에 숨은 변경값도 같은 시스템 저장에 포함한다.
- 기본값과 같은 override도 별도 설정으로 표시하며 취소는 override를 삭제하지 않는다.
- 입력 도중 DOM 재생성으로 포커스·스크롤을 잃지 않는다.
- 낮은 화면에서 표가 1~2행으로 압축되지 않고 모바일 가로 넘침을 막는다.

## 작업 1: 상태와 API/화면

- [x] `admin-modules/controller.test.ts`에 검색·페이지 초안·전환·유효성·부분 저장·실패·빈 목록 테스트를 먼저 작성하고 실패를 확인한다.
- [x] `types.ts`, `model.ts`, `render.ts`, `controller.ts`, `styles.css`와 `entries/admin-modules.ts`, Jinja 템플릿·Vite 엔트리를 구현한다.
- [x] 대상 Vitest, 타입 검사, 린트를 통과시킨다.

## 작업 2: 검증과 리뷰

- [x] `docs/specs/insights/03-admin-stats.md` 동기화, 프론트 게이트·문서 검사·관련 Python 테스트·전체 Vitest를 실행한다.
- [x] 최신 Vite 설정으로 빌드하고 Orca에서 실제 조회·검색·초안 원복·모바일/낮은 화면 높이를 확인한다.
- [x] 요청한 코드 리뷰 스킬의 독립 리뷰를 받고 중요한 문제를 실패 테스트 후 수정·검증한다.

## 실행 기록

- 사용자 지정 현재 브랜치에서 직접 구현한다. 기존 목업/캡처 파일은 로컬 참고 자료로 유지한다.
