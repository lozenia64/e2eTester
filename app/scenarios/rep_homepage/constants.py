"""대표홈페이지 시나리오의 채널 무관 도메인 상수 (단일 진실원천).

보험금청구(`compensation_charge`) → 결과확인(`compensation_result`) →
취소(`compensation_cancel`) 세 단계는 아래 청구 본문 문구로 서로 결합된다.
청구 단계가 이 문구로 테스트 청구를 등록하고, 결과/취소 단계가 같은 문구로
그 청구를 다시 찾아내 검증·취소하기 때문이다.

이 문구는 PC(HOM)·모바일(MHM) 채널이 공유하는 *도메인 규칙* 이므로
채널별 step 모듈에 각각 박지 않고 시나리오 계층에 단 한 번만 정의한다.
각 채널의 step 모듈은 이 값을 import 해서 사용한다.
"""

from __future__ import annotations

from typing import Final

# 보험금청구 단계가 입력하는 테스트 청구 본문. 결과확인·취소 단계가 이 문구로 청구를 재식별한다.
CLAIM_CONTENT_TEXT: Final[str] = "IT직원 테스트입니다. 바로 취소할 예정입니다."

# 결과/취소 목록 화면에서 청구를 찾을 때 비교하는 전체 문구.
TARGET_CLAIM_TEXT: Final[str] = CLAIM_CONTENT_TEXT

# 목록 카드/행에 본문이 잘려 표시될 수 있어, 부분 일치 탐색에 쓰는 앞부분 문구.
TARGET_CLAIM_TEXT_TRUNCATED: Final[str] = "IT직원 테스트입니다. 바로 취소할"
