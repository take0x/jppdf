import argparse
import time
from logging import DEBUG, INFO, basicConfig, getLogger
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

# Use 117 until the following bug is fixed
# https://github.com/SeleniumHQ/selenium/issues/13095
BROWSER_VERSION = "117"


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
        self.logger = getLogger(__name__)
        self.logger.setLevel(DEBUG if debug else INFO)
        basicConfig()

        self.path = path
        self.path_ja = path.with_stem(f"{path.stem}_ja")

        self.logger.info("Setting up...")
        self.options = Options(debug=debug)
        self.logger.info("Launching...")
        self.driver = Chrome(options=self.options)

    def __del__(self) -> None:
        self.driver.quit()

    def select_file(self) -> None:
        file_input = self.driver.find_element(By.NAME, "file")
        file_input.send_keys(str(self.path.resolve()))
        self.logger.info("Selected: '%s'", self.path.name)

    def click(self, xpath: str) -> None:
        wait = WebDriverWait(self.driver, 10)
        button = wait.until(ec.element_to_be_clickable((By.XPATH, xpath)))
        button.click()

    def translate(self) -> None:
        xpath = "//button/span[text()='翻訳']"
        self.click(xpath)
        self.logger.info("Translating...")

    def wait(self) -> None:
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
        xpath = "//button/span[text()='翻訳をダウンロード']"
        self.click(xpath)
        self.logger.info("Saving as: '%s'", self.path_ja.name)
        self.wait()

    def run(self) -> None:
        self.driver.get(Driver.url)
        self.select_file()
        self.translate()
        self.save()
        self.logger.info("Done.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="debug mode")
    parser.add_argument("path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    driver = Driver(args.path, debug=args.debug)
    driver.run()


if __name__ == "__main__":
    main()
