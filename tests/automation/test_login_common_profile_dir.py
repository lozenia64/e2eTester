"""프로필 경로 해석이 공용 함수 한 곳으로 모였는지 검증한다.

과거 hom/mhm login_common 은 각자 ``os.environ`` 을 읽어 `.env` 에 적은
``E2E_USER_DATA_DIR`` 을 무시했고, override 를 "루트"가 아니라 "최종 경로"로 해석해
실행 경로(access_common.executor)와 어긋났다. 이 테스트는 그 두 가지 회귀를 막는다.
"""

from __future__ import annotations

import app.automation.page_objects.hom.login_common as hom_common
import app.automation.page_objects.mhm.login_common as mhm_common
from app.core.settings import clear_settings_cache


def test_profile_names_stay_distinct_per_system() -> None:
    # 이름이 겹치면 두 시스템이 같은 프로필을 잠금 충돌로 공유한다.
    assert hom_common.USER_DATA_PROFILE_NAME == "chrome-profile"
    assert mhm_common.USER_DATA_PROFILE_NAME == "mhm-chrome-profile"


def test_override_is_a_root_and_profile_name_is_appended(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("E2E_USER_DATA_DIR", str(tmp_path))
    clear_settings_cache()
    try:
        assert hom_common.resolve_user_data_dir() == tmp_path / "chrome-profile"
        assert mhm_common.resolve_user_data_dir() == tmp_path / "mhm-chrome-profile"
    finally:
        clear_settings_cache()
