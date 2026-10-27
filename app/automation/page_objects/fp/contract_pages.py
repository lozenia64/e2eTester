"""FP 계약서 화면 분기 판정."""

from urllib.parse import urlparse

CONTRACT_WRITE_PAGE_PATH = "/fp/loan/sales02.do"
TM_CONTRACT_WRITE_PAGE_PATH = "/fp/loan/sales02_tm1.do"
CONTRACT_WRITE_PAGE_PATHS = frozenset({CONTRACT_WRITE_PAGE_PATH, TM_CONTRACT_WRITE_PAGE_PATH})
DOCUMENT_COMPLETE_PAGE_PATHS = frozenset({"/fp/loan/sales03.do", "/fp/loan/sales03_tm1.do"})


def is_contract_write_page(url: str) -> bool:
    return urlparse(url).path in CONTRACT_WRITE_PAGE_PATHS


def is_tm_contract_write_page(url: str) -> bool:
    return urlparse(url).path == TM_CONTRACT_WRITE_PAGE_PATH


def is_document_complete_page(url: str) -> bool:
    return urlparse(url).path in DOCUMENT_COMPLETE_PAGE_PATHS
