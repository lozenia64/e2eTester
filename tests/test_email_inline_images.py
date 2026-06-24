"""Outlook 호환 CID 인라인 스크린샷 MIME 구조 검증."""

from __future__ import annotations

import io
import re
import tempfile
from email import policy
from email.generator import BytesGenerator
from pathlib import Path

from app.notifications.run_completion_email import (
    InlineScreenshot,
    RunArtifact,
    _build_email_message,
    _make_screenshot_cid,
)


def _tiny_png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    )


def test_outlook_inline_image_mime_structure() -> None:
    with tempfile.TemporaryDirectory() as td:
        image_path = Path(td) / "final.png"
        image_path.write_bytes(_tiny_png())
        artifact = RunArtifact(
            module_id="login",
            module_name="로그인",
            order=10,
            seq=1,
            kind="screenshot",
            path=image_path,
            relative_path="artifacts/run/login/final.png",
            size_bytes=image_path.stat().st_size,
            system_code="FP",
            run_id="run_test",
        )
        cid = _make_screenshot_cid(artifact)
        inline = InlineScreenshot(artifact=artifact, cid=cid, status="passed", status_label="정상")
        html = f'<html><body><img src="cid:{cid}" width="600"></body></html>'

        message = _build_email_message(
            subject="test",
            from_addr="sender@gmail.com",
            plain_body="plain",
            html_body=html,
            inline_screenshots=[inline],
            log_attachments=[],
        )

        buffer = io.BytesIO()
        BytesGenerator(buffer, policy=policy.SMTP).flatten(message)
        raw = buffer.getvalue().decode("utf-8", errors="replace")

        assert "multipart/alternative" in raw
        assert "multipart/related" in raw
        assert f"<{cid}>" in raw
        assert "Content-ID" in raw
        assert "inline" in raw.lower()
        assert f"cid:{cid}" in html

        header_cid = re.search(r"Content-ID:\s*<([^>]+)>", raw)
        assert header_cid is not None
        assert header_cid.group(1) == cid

        assert message.get_content_type() == "multipart/related"
        children = message.get_payload()
        assert children[0].get_content_type() == "multipart/alternative"
        alternative_children = children[0].get_payload()
        assert alternative_children[0].get_content_type() == "text/plain"
        assert alternative_children[1].get_content_type() == "text/html"
        assert children[-1].get_content_type() == "image/png"
        assert children[-1]["Content-ID"] == f"<{cid}>"
        assert children[-1].get_content_disposition() == "inline"


def test_log_attachment_stays_outside_related_block() -> None:
    with tempfile.TemporaryDirectory() as td:
        image_path = Path(td) / "final.png"
        log_path = Path(td) / "execution.log"
        image_path.write_bytes(_tiny_png())
        log_path.write_text("log line\n", encoding="utf-8")

        image_artifact = RunArtifact(
            module_id="login",
            module_name="로그인",
            order=10,
            seq=1,
            kind="screenshot",
            path=image_path,
            relative_path="artifacts/run/login/final.png",
            size_bytes=image_path.stat().st_size,
            system_code="FP",
            run_id="run_test",
        )
        log_artifact = RunArtifact(
            module_id="login",
            module_name="로그인",
            order=10,
            seq=1,
            kind="log",
            path=log_path,
            relative_path="artifacts/run/login/execution.log",
            size_bytes=log_path.stat().st_size,
            system_code="FP",
            run_id="run_test",
        )
        cid = _make_screenshot_cid(image_artifact)
        inline = InlineScreenshot(artifact=image_artifact, cid=cid)

        message = _build_email_message(
            subject="test",
            from_addr="sender@gmail.com",
            plain_body="plain",
            html_body=f'<html><body><img src="cid:{cid}"></body></html>',
            inline_screenshots=[inline],
            log_attachments=[log_artifact],
        )

        assert message.get_content_type() == "multipart/mixed"
        related = message.get_payload()[0]
        assert related.get_content_type() == "multipart/related"
        assert related.get_payload()[0].get_content_type() == "multipart/alternative"
        assert message.get_payload()[-1].get_content_disposition() == "attachment"
