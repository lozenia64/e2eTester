"""MHM = 대표홈페이지 **모바일 채널** 드라이버 정의.

대표홈페이지 시나리오(1벌)를 모바일 셀렉터 어댑터(`app.systems.mhm.steps.*`)로 구동하기
위한 ``ChannelProfile`` 만 선언한다. PC(HOM)와의 차이는 ``mobile=True`` (모바일 디바이스
모드 적용)와 ``post_login_fragment`` 뿐이다. 워크플로 로직은
``app.scenarios.rep_homepage.executor.RepHomepageExecutor`` 에 단 한 번 존재한다.
"""

from __future__ import annotations

from app.scenarios.rep_homepage.channel import ChannelProfile, ChannelSteps
from app.systems.mhm.steps import (
    compensation_cancel,
    compensation_charge,
    compensation_result,
    contract_detail,
    contract_list,
    kakao_login,
    login_move,
    long_term_policy_certificate,
    main_access,
    phone_login,
)
from app.systems.mhm.steps import (
    login_common as common,
)

MOBILE_CHANNEL = ChannelProfile(
    code="mhm",
    execution_mode="mhm_workflow_step",
    label="MHM(모바일)",
    post_login_fragment="/myh/mai/MySubMain1000",
    mobile=True,
    common=common,
    steps=ChannelSteps(
        main_access=main_access,
        login_move=login_move,
        phone_login=phone_login,
        kakao_login=kakao_login,
        contract_list=contract_list,
        contract_detail=contract_detail,
        compensation_charge=compensation_charge,
        compensation_result=compensation_result,
        compensation_cancel=compensation_cancel,
        long_term_policy_certificate=long_term_policy_certificate,
    ),
)
