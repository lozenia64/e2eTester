from __future__ import annotations

import hom_login_common as common


def run(page, config: common.LoginConfig) -> str:
    common.open_url(page, config.base_url)
    common.maybe_close_home_popup(page)
    return "메인화면 접속 성공"