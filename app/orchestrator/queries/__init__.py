"""읽기 전용 질의 핸들러(CQRS query side).

라우트는 ``RunService``(커맨드 전용)가 아니라 이 패키지의 질의 핸들러를 주입받는다.
질의 핸들러는 프로젝션 기반 질의 포트만 소비하며, 유일한 예외는 단건 상세의
애그리거트 로드(blob + 로그 하이드레이션)다.
"""

from app.orchestrator.queries.admin_dashboard_queries import AdminDashboardQueries
from app.orchestrator.queries.daily_queries import DailyDashboardQueries
from app.orchestrator.queries.run_queries import RunQueries

__all__ = ["AdminDashboardQueries", "DailyDashboardQueries", "RunQueries"]
