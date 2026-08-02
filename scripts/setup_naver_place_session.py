#!/usr/bin/env python3
"""Open SmartPlace once and save a reusable Playwright login session."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright


SESSION_PATH = Path(".naver-place-session.json")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(locale="ko-KR", timezone_id="Asia/Seoul")
        page = context.new_page()
        page.goto("https://new.smartplace.naver.com/", wait_until="domcontentloaded")
        input("브라우저에서 로그인하고 업체의 [통계] 화면을 연 뒤 Enter를 누르세요: ")
        stats_url = page.url
        if not stats_url.startswith("https://new.smartplace.naver.com/"):
            raise SystemExit("스마트플레이스 화면 주소를 확인할 수 없습니다.")
        reservation_answer = input(
            "이제 [예약/주문]의 예약 통계 화면을 여세요. 연결하지 않으려면 skip을 입력하세요: "
        ).strip().lower()
        reservation_url = "" if reservation_answer == "skip" else page.url
        if reservation_url and not reservation_url.startswith("https://new.smartplace.naver.com/"):
            raise SystemExit("예약 통계 화면 주소를 확인할 수 없습니다.")
        context.storage_state(path=str(SESSION_PATH))
        browser.close()

    encoded = base64.b64encode(SESSION_PATH.read_bytes()).decode("ascii")
    print("GitHub Secrets에 로그인 세션과 통계 URL을 등록합니다.")
    try:
        subprocess.run(
            ["gh", "secret", "set", "NAVER_PLACE_STORAGE_STATE_B64"],
            input=encoded,
            text=True,
            check=True,
        )
        subprocess.run(
            ["gh", "secret", "set", "NAVER_PLACE_STATS_URL"],
            input=stats_url,
            text=True,
            check=True,
        )
        if reservation_url:
            subprocess.run(
                ["gh", "secret", "set", "NAVER_PLACE_RESERVATION_STATS_URL"],
                input=reservation_url,
                text=True,
                check=True,
            )
    finally:
        SESSION_PATH.unlink(missing_ok=True)
    print("등록 완료. 비밀번호는 저장되지 않았습니다.")


if __name__ == "__main__":
    main()
