import argparse
import sys
import time
from io import BytesIO
from logging import INFO, basicConfig, getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import requests
from pypdf import PdfReader
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

# Use 117 until the following bug is fixed
# https://github.com/SeleniumHQ/selenium/issues/13095
BROWSER_VERSION = "117"

# The timeout for the translation to finish
TRANSLATION_TIMEOUT = 20

logger = getLogger(__name__)
logger.setLevel(INFO)
basicConfig()


class Options(ChromeOptions):
    def __init__(self, *, debug: bool = False) -> None:
        super().__init__()

        self._download_dir = TemporaryDirectory()
        prefs: dict[str, Any] = {
            "download.default_directory": self._download_dir.name,
        }

        if not debug:
            # headless mode
            self.add_argument("--headless=new")

            # disable animations
            self.add_argument("--animation-duration-scale=0")

            # disable the download bubble
            prefs["download_bubble.partial_view_enabled"] = False

            self.make_normal_user_agent()

        # disable the navigator.webdriver flag
        self.add_argument("--disable-blink-features=AutomationControlled")

        # disable the logging
        self.set_capability("browserVersion", BROWSER_VERSION)
        self.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.add_experimental_option("prefs", prefs)

    def __del__(self) -> None:
        self._download_dir.cleanup()

    @property
    def download_dir(self) -> Path:
        return Path(self._download_dir.name)

    def make_normal_user_agent(self) -> None:
        options = ChromeOptions()
        options.add_argument("--headless=new")
        options.set_capability("browserVersion", BROWSER_VERSION)
        options.add_experimental_option("excludeSwitches", ["enable-logging"])

        with Chrome(options=options) as driver:
            headless_id = str(driver.execute_script("return navigator.userAgent"))
            normal_id = headless_id.replace("Headless", "")
            self.add_argument(f"user-agent={normal_id}")


class Driver:
    url = "https://translate.google.co.jp/?hl=ja&sl=auto&tl=ja&op=docs"

    def __init__(self, path: Path, *, debug: bool = False) -> None:
        self.path = path
        self.path_ja = path.with_stem(f"{path.stem}_ja")

        logger.info("Setting up...")
        self.options = Options(debug=debug)
        logger.info("Launching...")
        self.driver = Chrome(options=self.options)

    def __del__(self) -> None:
        self.driver.quit()

    def select_file(self) -> None:
        file_input = self.driver.find_element(By.NAME, "file")
        file_input.send_keys(str(self.path.resolve()))
        logger.info("Selected: '%s'", self.path.name)

    def wait_button(self, xpath: str, timeout: int) -> None:
        wait = WebDriverWait(self.driver, timeout)
        button = wait.until(ec.element_to_be_clickable((By.XPATH, xpath)))
        button.click()

    def translate(self) -> None:
        # click the translate button
        xpath = "//button/span[text()='翻訳']"
        button = self.driver.find_element(By.XPATH, xpath)
        button.click()

        logger.info("Translating...")

        # wait for the download button
        xpath = "//button/span[text()='翻訳をダウンロード']"
        self.wait_button(xpath, TRANSLATION_TIMEOUT)

    def wait_to_finish(self) -> None:
        timeout = 10
        path = self.options.download_dir / self.path.name

        for _ in range(timeout):
            time.sleep(1)
            if path.exists():
                self.path_ja.unlink(missing_ok=True)
                path.rename(self.path_ja)
                break
        else:
            msg = f"Timeout: {timeout} sec"
            raise TimeoutError(msg)

    def save(self) -> None:
        logger.info("Saving as: '%s'", self.path_ja.name)
        self.wait_to_finish()

    def run(self) -> None:
        self.driver.get(Driver.url)
        self.select_file()
        self.translate()
        self.save()
        logger.info("Done.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A tool to translate your PDF files into Japanese.",
    )
    parser.add_argument("--debug", action="store_true", help="debug mode")
    parser.add_argument("target", help="URL or path to PDF file")
    return parser.parse_args()


def is_url(target: str) -> bool:
    return target.startswith("http")


def download(url: str) -> Path:
    try:
        res = requests.get(url, timeout=3)
    except requests.exceptions.Timeout:
        logger.exception("Timeout occurred")
        sys.exit(1)

    pdf = PdfReader(BytesIO(res.content))

    if pdf.metadata is None:
        logger.error("Failed to get the title from the PDF metadata.")
        sys.exit(1)

    logger.info("Title: %s", pdf.metadata.title)
    basename = Path(url).name
    filename = Path(basename if basename.endswith(".pdf") else f"{basename}.pdf")
    filename.write_bytes(res.content)
    return filename


def main() -> None:
    args = parse_args()
    target: str = args.target
    path = download(target) if is_url(target) else Path(target)
    driver = Driver(path, debug=args.debug)
    driver.run()


if __name__ == "__main__":
    main()
