from argparse import Namespace
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.systems.hom.steps import login_common as common, login_move, main_access


def dump_state(page):
    return page.evaluate(
        """
        () => {
          const form = document.querySelector('#cellFrm');
          const formData = form ? Array.from(new FormData(form).entries()) : [];
          const inputs = Array.from(document.querySelectorAll('#cellFrm input, #cellFrm button, #cellFrm a.headline')).map((element) => ({
            tag: element.tagName.toLowerCase(),
            id: element.id || null,
            name: element.getAttribute('name'),
            type: element.getAttribute('type'),
            title: element.getAttribute('title'),
            value: element.value ?? null,
            text: (element.textContent || '').trim(),
            checked: 'checked' in element ? Boolean(element.checked) : null,
            className: element.className || null,
          }));
          return {
            url: location.href,
            title: document.title,
            formData,
            inputs,
          };
        }
        """
    )


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
        slow_mo=100,
        timeout_ms=20000,
        post_login_fragment='/my/',
        screenshot='artifacts/test.png',
    )
)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1200})
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
                'post_data': request.post_data,
            }

    page.on('request', on_request)

    main_access.run(page, cfg)
    login_move.run(page)
    common.fill_identity(page, cfg)
    before_state = dump_state(page)

    with page.expect_response(lambda response: 'hp-sms-request.json' in response.url, timeout=cfg.timeout_ms) as response_info:
        page.locator('#btnSendCrtfNo').click()

    response = response_info.value
    try:
        body = response.text()
    except Exception as exc:
        body = f'<failed to read body: {exc}>'

    after_state = dump_state(page)

    print(json.dumps({
        'dialogs': dialogs,
        'before': before_state,
        'captured': captured,
        'response': {
            'url': response.url,
            'status': response.status,
            'ok': response.ok,
            'headers': response.headers,
            'body': body,
        },
        'after': after_state,
    }, ensure_ascii=False, indent=2))

    context.close()
    browser.close()
