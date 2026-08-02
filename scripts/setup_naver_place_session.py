#!/usr/bin/env python3
"""Open SmartPlace once and save a reusable Playwright login session."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page


SESSION_PATH = Path(".naver-place-session.json")
TAB_SECRETS = (
    ("리포트", "NAVER_PLACE_REPORT_URL"),
    ("플레이스", "NAVER_PLACE_STATS_URL"),
    ("스마트콜", "NAVER_PLACE_SMARTCALL_STATS_URL"),
    ("예약주문", "NAVER_PLACE_RESERVATION_STATS_URL"),
    ("리뷰", "NAVER_PLACE_REVIEW_STATS_URL"),
)


def is_owner_page_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    smartplace_host = hostname == "smartplace.naver.com" or hostname.endswith(
        ".smartplace.naver.com"
    )
    return parsed.scheme == "https" and smartplace_host and parsed.path.rstrip("/") != ""


def latest_owner_page(context: "BrowserContext") -> "Page":
    candidates = [page for page in context.pages if is_owner_page_url(page.url)]
    if not candidates:
        raise SystemExit(
            "업체 통계 페이지를 찾지 못했습니다. 업체 카드에서 통계를 새로 연 뒤 다시 시도해주세요."
        )
    return candidates[-1]


def validate_tab_url(tab_name: str, url: str, saved_urls: set[str]) -> None:
    if not is_owner_page_url(url):
        raise SystemExit(f"{tab_name} 탭의 업체 관리 주소를 확인할 수 없습니다.")
    if url in saved_urls:
        raise SystemExit(
            f"{tab_name} 탭 주소가 이전 탭과 같습니다. 실제 [{tab_name}] 탭을 누른 뒤 다시 등록해주세요."
        )


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["gh", "secret", "set", name],
        input=value,
        text=True,
        check=True,
    )


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = context.new_page()
        page.goto("https://new.smartplace.naver.com/", wait_until="domcontentloaded")
        input("브라우저에서 로그인하고 대상 업체의 [통계] 메뉴를 연 뒤 Enter를 누르세요: ")
        latest_owner_page(context)
        tab_urls: dict[str, str] = {}
        saved_urls: set[str] = set()
        for tab_name, secret_name in TAB_SECRETS:
            input(f"통계의 [{tab_name}] 탭을 연 뒤 Enter를 누르세요: ")
            tab_url = latest_owner_page(context).url
            validate_tab_url(tab_name, tab_url, saved_urls)
            tab_urls[secret_name] = tab_url
            saved_urls.add(tab_url)
            print(f"{tab_name} 탭 주소 확인 완료")
        context.storage_state(path=str(SESSION_PATH))
        browser.close()

    encoded = base64.b64encode(SESSION_PATH.read_bytes()).decode("ascii")
    print("GitHub Secrets에 로그인 세션과 통계 URL을 등록합니다.")
    try:
        set_secret("NAVER_PLACE_STORAGE_STATE_B64", encoded)
        for secret_name, tab_url in tab_urls.items():
            set_secret(secret_name, tab_url)
    finally:
        SESSION_PATH.unlink(missing_ok=True)
    print("등록 완료. 비밀번호는 저장되지 않았습니다.")


if __name__ == "__main__":
    main()
