"""상황판 차단 스위치.

/wall 은 비인증 공개 라우트다(설계 D1). 앱이 사내망 밖으로 노출되는 상황에서
즉시 끌 수 있어야 한다(D2). 기본값은 true 다 — false 로 두면 배포 때 켜는 것을
잊어 "왜 안 되지" 사고가 난다.
"""

from app.core.settings import E2ESettings


def test_wall_is_enabled_by_default():
    assert E2ESettings().wall_enabled is True


def test_wall_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("E2E_WALL_ENABLED", "false")
    assert E2ESettings().wall_enabled is False
