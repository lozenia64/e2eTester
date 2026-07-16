"""채널(드라이버) 기술서와 셀렉터 어댑터 계약.

시나리오는 1벌(`executor.RepHomepageExecutor`)이고, 채널(PC/모바일) 차이는 전부
`ChannelProfile` 로만 표현된다. 새 채널을 추가한다는 것은 워크플로 전체를 복제하는
것이 아니라, 셀렉터 어댑터(step 모듈 묶음)를 구현하고 `ChannelProfile` 한 개를
선언하는 것을 의미한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class StepAdapter(Protocol):
    """단계 어댑터(채널별 step 모듈)가 따라야 하는 최소 계약.

    각 step 모듈은 `run(...)` 또는 시나리오가 호출하는 전용 함수를 노출한다.
    시그니처는 단계마다 다르므로(예: 로그인은 dialog_messages 를, 증명서는
    artifact_dir 를 추가로 받는다) 여기서는 존재만 표시하고, 호출은
    `RepHomepageExecutor` 의 단계 핸들러(`build_step_registry`)가 책임진다.
    """


@dataclass(frozen=True)
class ChannelSteps:
    """채널(드라이버)이 시나리오에 제공하는 도메인 액션 어댑터 묶음.

    각 항목은 해당 채널의 PageObject(예: ``app.automation.page_objects.hom.compensation_charge``)이며,
    시나리오의 단계 핸들러가 채널과 무관하게 호출하는 단일 계약이다. PC/모바일은 같은 이름의
    액션을 서로 다른 셀렉터·UI 텍스트로 구현해 여기에 주입한다.
    """

    main_access: StepAdapter
    login_move: StepAdapter
    phone_login: StepAdapter
    kakao_login: StepAdapter
    contract_list: StepAdapter
    contract_detail: StepAdapter
    compensation_charge: StepAdapter
    compensation_result: StepAdapter
    compensation_cancel: StepAdapter
    long_term_policy_certificate: StepAdapter
    marketing_consent_apply: StepAdapter
    marketing_consent_withdraw: StepAdapter


@dataclass(frozen=True)
class ChannelProfile:
    """대표홈페이지 채널(PC/모바일) 드라이버 기술서.

    - ``code``                : 시스템 코드 ("hom" / "mhm")
    - ``execution_mode``      : manifest 의 ``execution_mode`` 와 매칭되는 식별자
    - ``label``               : 로그/에러 메시지에 쓰는 사람용 이름
    - ``post_login_fragment`` : 로그인 성공 판정에 쓰는 메인 화면 URL 조각
    - ``mobile``              : True 면 build_runtime 에서 모바일 디바이스 모드를 적용
    - ``common``              : 채널의 ``login_common`` 어댑터 모듈 (브라우저 기동/설정 헬퍼)
    - ``steps``               : 채널의 단계 어댑터 묶음
    """

    code: str
    execution_mode: str
    label: str
    post_login_fragment: str
    mobile: bool
    common: object
    steps: ChannelSteps
