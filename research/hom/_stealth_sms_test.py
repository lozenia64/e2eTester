from argparse import Namespace
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.systems.hom.steps import login_common as common, login_move, main_access

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {
  get: () => undefined,
});
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', {
  get: () => ['ko-KR', 'ko', 'en-US', 'en'],
});
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5],
});
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters && parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
"""

cfg = common.build_config(
    Namespace(
        env_file='.env',
        base_url=None,
        name=None,
        birthdate=None,
        gender=None,
        residency=None,
        carrier=None,
        phone_number=None,
        phone_prefix=None,
        otp_code=None,
        headless=False,
        slow_mo=0,
        timeout_ms=20000,
        post_login_fragment='/my/',
        screenshot='artifacts/test.png',
    )
)

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        channel='chrome',
        headless=False,
        args=['--disable-blink-features=AutomationControlled'],
    )
    context = browser.new_context(viewport={'width': 1440, 'height': 1200}, locale='ko-KR')
    context.add_init_script(STEALTH_SCRIPT)
    common.grant_browser_permissions(context, cfg.base_url)
    page = context.new_page()
    page.set_default_timeout(cfg.timeout_ms)
    page.set_default_navigation_timeout(cfg.timeout_ms)
    dialogs = common.add_dialog_logger(page)
    captured = {}

    def on_request(request):
        if 'hp-sms-request.json' in request.url:
            captured['request'] = {
                'url': request.url,
                'method': request.method,
                'headers': request.headers,
                'post_data_prefix': (request.post_data or '')[:500],
            }

    page.on('request', on_request)
    main_access.run(page, cfg)
    login_move.run(page)
    common.fill_identity(page, cfg)
    fingerprint = page.evaluate("""() => ({ webdriver: navigator.webdriver, languages: navigator.languages, pluginsLength: navigator.plugins.length, notificationPermission: Notification.permission, chromeKeys: window.chrome ? Object.keys(window.chrome).slice(0, 10) : [] })""")

    with page.expect_response(lambda response: 'hp-sms-request.json' in response.url, timeout=cfg.timeout_ms) as response_info:
        page.locator('#btnSendCrtfNo').click()
    response = response_info.value

    print(json.dumps({
        'dialogs': dialogs,
        'fingerprint': fingerprint,
        'request': captured.get('request'),
        'response': {
            'status': response.status,
            'ok': response.ok,
            'body': response.text(),
        },
    }, ensure_ascii=False, indent=2))

    context.close()
    browser.close()
