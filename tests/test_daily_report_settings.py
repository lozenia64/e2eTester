"""일간 리포트 발송 스위치.

메일은 사람 받은편지함으로 나가는 되돌릴 수 없는 부수효과다. 상황판(E2E_WALL_ENABLED)을
기본 true 로 둔 것과 반대로, 여기는 기본 false 다 — 안 켜면 "안 나가는" 것이고
켜면 "잘못 나가는" 것이라 실패 방향이 다르다(설계 D3).
"""

from app.core.settings import E2ESettings


def test_daily_report_is_disabled_by_default():
    assert E2ESettings().daily_report_enabled is False


def test_daily_report_can_be_enabled_by_env(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_ENABLED", "true")
    assert E2ESettings().daily_report_enabled is True


def test_daily_report_cron_defaults_to_none(monkeypatch):
    monkeypatch.delenv("E2E_EMAIL_DAILY_REPORT_CRON", raising=False)
    assert E2ESettings().daily_report_cron is None


def test_daily_report_cron_reads_env(monkeypatch):
    monkeypatch.setenv("E2E_EMAIL_DAILY_REPORT_CRON", "30 7 * * *")
    assert E2ESettings().daily_report_cron == "30 7 * * *"
