#!/usr/bin/env python3
"""Open SmartPlace once and save a reusable Playwright login session."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


SESSION_PATH = Path(".naver-place-session.json")
TAB_SECRETS = (
    ("리포트", "NAVER_PLACE_REPORT_URL"),
    ("플레이스", "NAVER_PLACE_STATS_URL"),
    ("스마트콜", "NAVER_PLACE_SMARTCALL_STATS_URL"),
    ("예약주문", "NAVER_PLACE_RESERVATION_STATS_URL"),
    ("리뷰", "NAVER_PLACE_REVIEW_STATS_URL"),
)


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["gh", "secret", "set", name],
        input=value,
        text=True,
        check=True,
    )


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = context.new_page()
        page.goto("https://new.smartplace.naver.com/", wait_until="domcontentloaded")
        input("브라우저에서 로그인하고 대상 업체의 [통계] 메뉴를 연 뒤 Enter를 누르세요: ")
        tab_urls: dict[str, str] = {}
        for tab_name, secret_name in TAB_SECRETS:
            input(f"통계의 [{tab_name}] 탭을 연 뒤 Enter를 누르세요: ")
            tab_url = page.url
            if not tab_url.startswith("https://new.smartplace.naver.com/"):
                raise SystemExit(f"{tab_name} 탭의 스마트플레이스 주소를 확인할 수 없습니다.")
            tab_urls[secret_name] = tab_url
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
