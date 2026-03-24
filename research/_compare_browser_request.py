from argparse import Namespace
import json

from playwright.sync_api import sync_playwright

import hom_login_phone as app


cfg = app.build_config(
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

cases = [
    {"name": "chromium_headed", "launch": {"headless": False}},
    {"name": "chrome_headed", "launch": {"channel": "chrome", "headless": False}},
]

results = []

with sync_playwright() as pw:
    for case in cases:
        browser = pw.chromium.launch(**case["launch"])
        context = browser.new_context(viewport={"width": 1440, "height": 1200})
        app.grant_browser_permissions(context, cfg.base_url)
        page = context.new_page()
        page.set_default_timeout(cfg.timeout_ms)
        page.set_default_navigation_timeout(cfg.timeout_ms)
        dialogs = app.add_dialog_logger(page)
        captured = {}

        def on_request(request):
            if 'hp-sms-request.json' in request.url:
                captured['request'] = {
                    'url': request.url,
                    'method': request.method,
                    'headers': request.headers,
                    'post_data_prefix': (request.post_data or '')[:400],
                }

        page.on('request', on_request)

        try:
            app.navigate_to_phone_login(page, cfg.base_url)
            app.fill_identity(page, cfg)
            with page.expect_response(lambda response: 'hp-sms-request.json' in response.url, timeout=cfg.timeout_ms) as response_info:
                page.locator('#btnSendCrtfNo').click()
            response = response_info.value
            body = response.text()
            results.append({
                'case': case['name'],
                'dialogs': dialogs,
                'request': captured.get('request'),
                'response': {
                    'status': response.status,
                    'ok': response.ok,
                    'body': body,
                },
            })
        except Exception as exc:
            results.append({
                'case': case['name'],
                'dialogs': dialogs,
                'request': captured.get('request'),
                'error': repr(exc),
            })
        finally:
            context.close()
            browser.close()

print(json.dumps(results, ensure_ascii=False, indent=2))
