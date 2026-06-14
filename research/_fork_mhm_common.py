"""One-off: fork HOM login_common.py -> MHM login_common.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "app" / "systems" / "hom" / "steps" / "login_common.py").read_text(encoding="utf-8")
text = text.replace(
    'DEFAULT_BASE_URL: Final[str] = "https://www.hwgeneralins.com"',
    'DEFAULT_BASE_URL: Final[str] = "https://m.hwgeneralins.com"',
)
text = text.replace(
    'DEFAULT_USER_DATA_DIR: Final[Path] = Path.home() / ".e2etester" / "chrome-profile"',
    'DEFAULT_USER_DATA_DIR: Final[Path] = Path.home() / ".e2etester" / "mhm-chrome-profile"',
)
text = text.replace(
    'POST_LOGIN_MAIN_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"/my/main\\.do")',
    'POST_LOGIN_MAIN_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"/m/my/main\\.do|/my/main\\.do")',
)
text = text.replace("hwgeneralins-login-result.png", "mhwgeneralins-login-result.png")
text = text.replace('"viewport": {"width": 1440, "height": 1200}', '"viewport": {"width": 390, "height": 844}')
text = text.replace(
    'DEFAULT_USER_DATA_DIR_NAME: Final[str] = "chrome-profile"',
    'DEFAULT_USER_DATA_DIR_NAME: Final[str] = "mhm-chrome-profile"',
) if 'DEFAULT_USER_DATA_DIR_NAME' in text else text
(ROOT / "app" / "systems" / "mhm" / "steps" / "login_common.py").write_text(text, encoding="utf-8")
print("wrote app/systems/mhm/steps/login_common.py")
