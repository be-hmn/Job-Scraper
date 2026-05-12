"""
Selenium 기반 스크래퍼 공통 베이스

SeleniumBase UC Mode (Undetected Chrome):
  - undetected-chromedriver 기반으로 Cloudflare, Akamai 등 봇 탐지 우회
  - headless 환경에서도 navigator.webdriver = false 유지
  - Chrome 버전 자동 감지 및 패치

딜레이: random.uniform(3, 7) 초 — 인간다운 체류 시간 부여
"""

import os
import random
import time
import logging
from typing import Optional

from seleniumbase import SB
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# 요청 간 대기 범위 (초)
_DELAY_MIN = 3.0
_DELAY_MAX = 7.0

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# GitHub Actions / CI 환경에서 추가할 Chrome 옵션
_CI_CHROME_ARGS = "--headless=new,--no-sandbox,--disable-dev-shm-usage,--disable-gpu"
_IS_CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"


def _find_chrome() -> str:
    """Chrome 실행파일 경로 탐색. CI 환경이면 시스템 chrome을 우선 탐색."""
    import subprocess

    env_bin = os.getenv("CHROME_BIN", "")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    # CI(Ubuntu) 환경: which google-chrome / chromium-browser
    if _IS_CI:
        for cmd in ("google-chrome", "chromium-browser", "chromium", "chrome"):
            try:
                result = subprocess.run(
                    ["which", cmd], capture_output=True, text=True, timeout=5
                )
                path = result.stdout.strip()
                if path and os.path.isfile(path):
                    return path
            except Exception:
                pass

    for p in CHROME_CANDIDATES:
        if os.path.isfile(p):
            return p
    local = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local, "Google", "Chrome", "Application", "chrome.exe")
    if os.path.isfile(candidate):
        return candidate
    try:
        result = subprocess.run(["where", "chrome"], capture_output=True, text=True)
        path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return ""


class SeleniumBaseScraper(BaseScraper):
    """
    SeleniumBase UC Mode를 사용하는 스크래퍼 베이스.

    UC Mode 특징:
    - navigator.webdriver 패치 → 봇 탐지 우회
    - Cloudflare Turnstile, hCaptcha 자동 처리
    - headless=True 에서도 정상 동작
    """

    def _get_sb_context(self):
        """
        SeleniumBase SB 컨텍스트 매니저 반환.
        with self._get_sb_context() as sb: 형태로 사용.
        """
        chrome_path = _find_chrome()
        if not chrome_path and not _IS_CI:
            raise RuntimeError(
                "Chrome 브라우저를 찾을 수 없습니다.\n"
                "해결 방법:\n"
                "  1) Chrome 설치: https://www.google.com/chrome/\n"
                "  2) 또는 .env 에 CHROME_BIN=C:\\path\\to\\chrome.exe 설정"
            )

        # CI 환경: --no-sandbox 등 필수 옵션 추가, Chrome 경로 없어도 시스템 chrome 사용
        base_args = "--no-sandbox,--disable-gpu,--window-size=1920,1080"
        if _IS_CI:
            chromium_args = f"--headless=new,{base_args},--disable-dev-shm-usage"
            logger.info("[SeleniumBase] CI 환경: headless + no-sandbox 옵션 적용")
        else:
            chromium_args = base_args

        sb_kwargs = dict(
            uc=True,
            headless=True,
            chromium_arg=chromium_args,
        )
        if chrome_path:
            sb_kwargs["binary_location"] = chrome_path

        return SB(**sb_kwargs)

    def _wait_and_get(
        self,
        sb,
        url: str,
        wait_selector: str,
        timeout: int = 20,
    ) -> bool:
        """
        URL 로드 후 특정 CSS 셀렉터가 나타날 때까지 대기.
        인간다운 딜레이(3~7초) 포함.
        """
        try:
            sb.open(url)
            # 인간다운 체류 시간
            time.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))
            sb.wait_for_element(wait_selector, timeout=timeout)
            return True
        except Exception as e:
            logger.warning("[%s] 페이지 로드 실패: %s | %s", self.site_name, e, url)
            return False
