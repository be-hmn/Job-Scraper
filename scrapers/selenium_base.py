"""
Selenium 기반 스크래퍼 공통 베이스
SPA(React/Next.js) 사이트 크롤링에 사용
"""

import time
import logging
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_chrome() -> str:
    """Chrome 실행파일 경로 탐색. 없으면 빈 문자열 반환."""
    import os, subprocess
    # 환경변수 CHROME_BIN 우선
    env_bin = os.getenv("CHROME_BIN", "")
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    # 고정 경로 탐색
    for p in CHROME_CANDIDATES:
        if os.path.isfile(p):
            return p
    # LOCALAPPDATA 탐색
    local = os.getenv("LOCALAPPDATA", "")
    candidate = os.path.join(local, "Google", "Chrome", "Application", "chrome.exe")
    if os.path.isfile(candidate):
        return candidate
    # where 명령으로 PATH 탐색
    try:
        result = subprocess.run(["where", "chrome"], capture_output=True, text=True)
        path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return ""


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """헤드리스 Chrome 드라이버 생성.
    Chrome이 없으면 RuntimeError를 발생시켜 스크래퍼가 graceful하게 실패하도록 한다.
    Chrome 설치: https://www.google.com/chrome/
    또는 환경변수 CHROME_BIN 에 chrome.exe 경로를 지정하세요.
    """
    chrome_path = _find_chrome()
    if not chrome_path:
        raise RuntimeError(
            "Chrome 브라우저를 찾을 수 없습니다.\n"
            "해결 방법:\n"
            "  1) Chrome 설치: https://www.google.com/chrome/\n"
            "  2) 또는 .env 에 CHROME_BIN=C:\\path\\to\\chrome.exe 설정"
        )

    opts = Options()
    opts.binary_location = chrome_path
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


class SeleniumBaseScraper(BaseScraper):
    """Selenium을 사용하는 스크래퍼의 공통 베이스"""

    def _get_driver(self) -> webdriver.Chrome:
        return build_driver(headless=True)

    def _wait_and_get(
        self,
        driver: webdriver.Chrome,
        url: str,
        wait_selector: str,
        timeout: int = 15,
    ) -> bool:
        """URL 로드 후 특정 셀렉터가 나타날 때까지 대기"""
        try:
            driver.get(url)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
            )
            time.sleep(1.0)  # 추가 렌더링 대기
            return True
        except Exception as e:
            logger.warning("[%s] 페이지 로드 실패: %s | %s", self.site_name, e, url)
            return False
