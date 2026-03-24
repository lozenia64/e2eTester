import json
from playwright.sync_api import sync_playwright

cases = [
    {"name": "chromium_headed", "launch": {"headless": False}},
    {"name": "chrome_headed", "launch": {"channel": "chrome", "headless": False}},
]

script = """
() => ({
  webdriver: navigator.webdriver,
  userAgent: navigator.userAgent,
  language: navigator.language,
  languages: navigator.languages,
  platform: navigator.platform,
  vendor: navigator.vendor,
  hardwareConcurrency: navigator.hardwareConcurrency,
  deviceMemory: navigator.deviceMemory ?? null,
  pluginsLength: navigator.plugins.length,
  mimeTypesLength: navigator.mimeTypes.length,
  hasChrome: Boolean(window.chrome),
  chromeKeys: window.chrome ? Object.keys(window.chrome).slice(0, 20) : [],
  notificationPermission: Notification.permission,
})
"""

results = []
with sync_playwright() as pw:
    for case in cases:
        browser = pw.chromium.launch(**case['launch'])
        context = browser.new_context()
        page = context.new_page()
        page.set_content('<html><body>probe</body></html>')
        results.append({'case': case['name'], 'fingerprint': page.evaluate(script)})
        context.close()
        browser.close()

print(json.dumps(results, ensure_ascii=False, indent=2))
