"""시스템별 로그인 Flow는 ``flows/{system}/`` 에 정의한다.

접속 점검 공용 ``main_access`` 는 ``access_flow.AccessMainFlow`` 를 사용한다.
"""

from app.automation.flows.access.access_flow import AccessMainFlow

__all__ = ["AccessMainFlow"]
