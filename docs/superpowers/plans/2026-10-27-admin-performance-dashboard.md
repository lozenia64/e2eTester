# 관리자 성과 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 승인된 성과 보고형 목업을 실데이터 기반 관리자 대시보드로 구현한다.
**Architecture:** StatsService의 기준 초 계산을 공유하고 월간 성과 읽기 모델을 추가한다. 독립 Vite 엔트리가 성과·일간·커버리지 API를 각각 갱신한다.
**Tech Stack:** Python/FastAPI, Jinja, TypeScript/Vite, ECharts, CSS.
**Spec:** `docs/superpowers/specs/2026-10-27-admin-performance-dashboard-design.md`

## Global Constraints

- 관리자 전용, 한국어 UI, 추가 런타임 의존성·CDN 없음.
- 한국 달력 기준 월간 집계. 기존 ADMIN_VISIBLE_RUN_STATUSES·PASSED 절감 산식 유지.
- 모션 감소 설정 존중, 최초 모션 재실행 금지, 갱신 실패 시 마지막 성공 데이터 보존.
- 기존 커버리지·일간 실행 링크 보존. manifest·자동화 코드 변경 없음.

## Review Focus

- 전월이 짧거나 윤년인 경우 비교 종료는 전월 마지막 날의 끝이다.
- 전월 0·기준 초 0·실행 없음은 오류와 구분한다.
- 갱신 중 포커스·열린 산정 기준을 보존하고 중복 요청을 차단한다.
- 일부 API 실패가 다른 영역의 성공을 지우지 않아야 한다.
- 실제 차트 로드 실패 시에도 합계·표 데이터가 읽혀야 한다.

## 실행 방식

사용자의 설계 승인과 구현 진행 승인에 따라 이 세션에서 직접 구현한다. 기존 비-main 작업 브랜치에서 현재 작업 디렉터리를 사용한다.
미추적 설계/목업은 보존한다. 변경을 커밋하거나 공유 브랜치에 반영하지 않고 검토 가능한 diff로 남긴다.

### Task 1: 월간 성과 집계와 API

**Files:** `app/contexts/insights/application/savings_basis.py`, `admin_performance.py`, `stats_service.py`, `app/api/routes_admin.py`, `tests/test_admin_performance.py`
**Interfaces:** `performance_periods(now)`와 `build_performance(now, runs, modules, systems, basis)` 순수 집계; `StatsService.get_performance_dashboard(now=None)` 관리자 읽기 API용 dict.

- [x] 테스트로 월 경계·짧은 전월·한국 자정·PASSED 산식·시스템/누적 합계·0 기준·빈 기간·override·API 권한을 명시한다.
- [x] 새 테스트 실패 확인 후 shared basis와 집계를 구현한다. 기간 조회는 전월 시작~현재 1회씩, Run/모듈 인덱스 이용.
- [x] 기존 StatsService 산식에 shared basis를 적용하고 기존 통계와 일치함을 검증한다.
- [x] 새 API를 관리자 의존성과 연결하고 관련 Python 테스트를 실행한다.

### Task 2: 성과 보고 화면과 갱신

**Files:** `app/web/frontend/admin-dashboard/{types,render,controller,charts,styles}.ts/css`, `entries/admin-dashboard.ts`, `templates/admin/{base,index}.html`, `vite.config.ts`
**Interfaces:** 독립 영역별 `DashboardController.refresh()`; 순수 렌더 함수와 ECharts 로더.

- [x] Vitest로 부분 실패 보존·중복 갱신·숨김 폴링·첫 모션 1회·포커스 보존·0 상태·텍스트 이스케이프를 먼저 검증한다.
- [x] 목업 ③의 위계·색상·모션으로 Jinja/CSS와 데이터 렌더를 구현한다.
- [x] 모든 실행 링크·7일 슬롯·일간 카드 유지. 산정 펼침과 차트 데이터 표 추가.
- [x] ECharts를 동적 로딩하고 실패해도 목록·표를 유지한다. ResizeObserver/동작 감소를 적용한다.
- [x] 타입 검사·린트·Vitest·빌드로 확인한다. 기존 static JS 참조는 제거한다.

### Task 3: 문서·통합 검증·검토

**Files:** `docs/E2E_ARCHITECTURE.md`, `docs/specs/insights/03-admin-stats.md`, 본 계획 및 설계 문서.

- [x] API와 산정 기준·수용 기준을 SSOT 문서에 반영한다.
- [x] 관련 회귀 테스트·문서/프런트 게이트 및 전체 게이트(full)를 실행한다.
- [x] 프로젝트 브라우저 스킬에 따라 실제 관리자 화면을 390/768/1440/1920에서 확인한다.
- [x] 새 검토 에이전트로 전체 diff를 검토하고 중요한 문제를 수정한다.
- [x] 결과와 남은 제한을 보고한다.
