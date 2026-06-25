"""List Gemini models available to the configured API key.

Usage (from repo root):
    python research/list_gemini_models.py
    python research/list_gemini_models.py --all
    python research/list_gemini_models.py --json

Reads GEMINI_API_KEY and E2E_GEMINI_SSL_VERIFY from the environment / .env file.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ai.gemini_http import DEFAULT_GEMINI_ENDPOINT, load_gemini_transport_settings
from app.core.settings import get_settings

GENERATE_CONTENT_METHOD = "generateContent"


def _fetch_models(*, api_key: str, verify_ssl: bool, endpoint: str) -> list[dict]:
    models: list[dict] = []
    page_token: str | None = None

    while True:
        query = f"key={api_key}"
        if page_token:
            query += f"&pageToken={page_token}"
        api_url = f"{endpoint}/models?{query}"
        http_request = request.Request(api_url, method="GET")
        ssl_context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
        try:
            with request.urlopen(http_request, timeout=30, context=ssl_context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Gemini API request failed: {exc.reason}") from exc

        models.extend(payload.get("models") or [])
        page_token = payload.get("nextPageToken")
        if not page_token:
            break

    return models


def _supports_generate_content(model: dict) -> bool:
    methods = model.get("supportedGenerationMethods") or []
    return GENERATE_CONTENT_METHOD in methods


def _model_id(model: dict) -> str:
    name = str(model.get("name") or "")
    if name.startswith("models/"):
        return name.split("/", 1)[1]
    return name


def _print_table(models: list[dict], *, show_methods: bool) -> None:
    if not models:
        print("조회된 모델이 없습니다.")
        return

    rows: list[tuple[str, str, str]] = []
    for model in sorted(models, key=_model_id):
        model_id = _model_id(model)
        display_name = str(model.get("displayName") or "-")
        methods = ", ".join(model.get("supportedGenerationMethods") or [])
        rows.append((model_id, display_name, methods))

    id_width = max(len("model_id"), *(len(row[0]) for row in rows))
    name_width = max(len("display_name"), *(len(row[1]) for row in rows))

    header = f"{'model_id'.ljust(id_width)}  {'display_name'.ljust(name_width)}"
    if show_methods:
        header += "  supported_methods"
    print(header)
    print("-" * len(header))
    for model_id, display_name, methods in rows:
        line = f"{model_id.ljust(id_width)}  {display_name.ljust(name_width)}"
        if show_methods:
            line += f"  {methods}"
        print(line)

    print()
    print(f"총 {len(rows)}개 모델")


def main() -> int:
    parser = argparse.ArgumentParser(description="List Gemini models for the configured API key.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="generateContent 지원 여부와 관계없이 전체 모델을 출력합니다.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="표 대신 원본 JSON 배열을 출력합니다.",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_GEMINI_ENDPOINT,
        help=f"Gemini API endpoint (default: {DEFAULT_GEMINI_ENDPOINT})",
    )
    args = parser.parse_args()

    settings = get_settings()
    api_key = settings.gemini_api_key_str()
    if not api_key or api_key == "your_actual_api_key":
        print("GEMINI_API_KEY 가 .env 또는 환경 변수에 설정되어 있지 않습니다.", file=sys.stderr)
        return 1

    transport = load_gemini_transport_settings()
    models = _fetch_models(
        api_key=api_key,
        verify_ssl=transport.verify_ssl,
        endpoint=args.endpoint.rstrip("/"),
    )

    if not args.all:
        models = [model for model in models if _supports_generate_content(model)]

    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return 0

    label = "전체" if args.all else f"{GENERATE_CONTENT_METHOD} 호출 가능"
    print(f"Gemini 모델 목록 ({label})")
    print(f"endpoint: {args.endpoint}")
    print(f"ssl_verify: {transport.verify_ssl}")
    print()
    _print_table(models, show_methods=args.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
