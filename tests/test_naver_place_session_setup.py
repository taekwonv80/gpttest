from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "setup_naver_place_session.py"
SPEC = importlib.util.spec_from_file_location("setup_naver_place_session", MODULE_PATH)
setup = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(setup)


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeContext:
    def __init__(self, urls: list[str]) -> None:
        self.pages = [FakePage(url) for url in urls]


class SessionSetupTests(unittest.TestCase):
    def test_owner_page_rejects_smartplace_home(self) -> None:
        self.assertFalse(setup.is_owner_page_url("https://new.smartplace.naver.com/"))
        self.assertTrue(
            setup.is_owner_page_url("https://new.smartplace.naver.com/bizes/123/reports")
        )

    def test_latest_owner_page_uses_newly_opened_business_tab(self) -> None:
        context = FakeContext(
            [
                "https://new.smartplace.naver.com/",
                "https://new.smartplace.naver.com/bizes/123/reports",
                "https://new.smartplace.naver.com/bizes/123/place",
            ]
        )
        self.assertEqual(setup.latest_owner_page(context).url.endswith("/place"), True)

    def test_duplicate_tab_url_is_rejected(self) -> None:
        url = "https://new.smartplace.naver.com/bizes/123/reports"
        with self.assertRaises(SystemExit):
            setup.validate_tab_url("플레이스", url, {url})


if __name__ == "__main__":
    unittest.main()
