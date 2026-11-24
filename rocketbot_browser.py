import time
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import (
    InvalidSessionIdException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


@dataclass(frozen=True)
class Inspection:
    robot_selected: bool
    robot_name: Optional[str]
    play_xpath: Optional[str]
    play_element: Optional[WebElement]
    running_xpath: Optional[str]
    running_element: Optional[WebElement]
    error_xpath: Optional[str]
    error_element: Optional[WebElement]
    page_title: str
    page_url: str
    inspected_text: str


class RocketbotBrowser:
    RUN_XPATH = '//*[@id="__layout"]/main/div/div/div[1]/div[2]/div/button[4]'
    STOP_XPATH = '//*[@id="__layout"]/main/div/div/div[1]/div[2]/div/button[5]'
    SAVE_XPATH = '//*[@id="__layout"]/main/div/div/div[1]/div[2]/div/button[3]'

    def __init__(self, editor_url: str, robot_name: str,
                 headless: bool, logger) -> None:
        self.editor_url = editor_url
        self.robot_name = robot_name
        self.headless = headless
        self.logger = logger
        self.driver: Optional[webdriver.Chrome] = None

    def start(self) -> None:
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        self.driver = webdriver.Chrome(options=options)
        self.logger.info("Chrome de Selenium iniciado en sesión propia")

    def open_editor(self) -> None:
        if self.driver is None:
            raise RuntimeError("El navegador no fue iniciado")
        self.driver.get(self.editor_url)
        WebDriverWait(self.driver, 20).until(
            lambda browser: browser.execute_script("return document.readyState")
            == "complete"
        )
        time.sleep(3)

    def _elements_with_xpath(self, xpath: str) -> list[WebElement]:
        if self.driver is None:
            return []
        try:
            return list(self.driver.find_elements(By.XPATH, xpath))
        except Exception:
            return []

    def inspect(self) -> Inspection:
        if self.driver is None:
            raise RuntimeError("El navegador no fue iniciado")

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        robot_selected = self.robot_name in body_text

        play_element = None
        play_xpath = None
        for xpath in (self.RUN_XPATH,):
            try:
                element = self.driver.find_element(By.XPATH, xpath)
                text = (element.text or "").strip().lower()
                if text == "run" and element.is_displayed():
                    play_element = element
                    play_xpath = xpath
                    break
            except NoSuchElementException:
                continue

        running_element = self._find_status_element(
            ("running", "ejecutando", "en ejecución", "in progress")
        )
        error_element = self._find_status_element(
            ("error", "fallida", "failed", "excepción")
        )

        return Inspection(
            robot_selected=robot_selected,
            robot_name=self.robot_name if robot_selected else None,
            play_xpath=play_xpath,
            play_element=play_element,
            running_xpath=(
                self._xpath_for(running_element) if running_element else None
            ),
            running_element=running_element,
            error_xpath=self._xpath_for(error_element) if error_element else None,
            error_element=error_element,
            page_title=self.driver.title,
            page_url=self.driver.current_url,
            inspected_text=body_text[:4000],
        )

    def _find_status_element(self, terms: tuple[str, ...]) -> Optional[WebElement]:
        if self.driver is None:
            return None
        candidates = self._elements_with_xpath(
            "//*[contains(@class,'status') or contains(@class,'running') "
            "or contains(@class,'error') or @role='status' or @aria-live]"
        )
        for element in candidates:
            try:
                text = " ".join(
                    (element.text or "", element.get_attribute("title") or "",
                     element.get_attribute("aria-label") or "")
                ).strip().lower()
                if any(term in text for term in terms):
                    return element
            except Exception:
                continue
        return None

    def _xpath_for(self, element: WebElement) -> str:
        if self.driver is None:
            return ""
        result = self.driver.execute_script(
            """
            function getXPath(el) {
              if (el.id) return '//*[@id=' + JSON.stringify(el.id) + ']';
              const parts = [];
              for (; el && el.nodeType === 1; el = el.parentNode) {
                let index = 1;
                let sibling = el.previousSibling;
                for (; sibling; sibling = sibling.previousSibling) {
                  if (sibling.nodeType === 1 && sibling.nodeName === el.nodeName) index++;
                }
                const part = el.nodeName.toLowerCase() + '[' + index + ']';
                parts.unshift(part);
              }
              return '/' + parts.join('/');
            }
            return getXPath(arguments[0]);
            """,
            element,
        )
        return str(result)

    def is_real_active_execution(self) -> bool:
        inspection = self.inspect()
        return inspection.running_element is not None

    def start_robot(self, inspection: Inspection) -> bool:
        if inspection.play_element is None:
            return False
        try:
            if not inspection.play_element.is_displayed():
                return False
            if not inspection.play_element.is_enabled():
                return False
            inspection.play_element.click()
            return True
        except (NoSuchElementException, InvalidSessionIdException):
            return False

    def wait_for_result(self, timeout_seconds: int,
                        logger) -> tuple[str, str]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            inspection = self.inspect()
            if inspection.error_element is not None:
                return "EJECUCION_ERROR", (
                    inspection.error_element.text
                    or "Se detectó un indicador de error real"
                )
            if inspection.running_element is not None:
                time.sleep(2)
                continue

            if self._completion_evidence(inspection):
                return "EJECUCION_COMPLETADA", "Finalización confirmada por evidencia real"
            time.sleep(2)
        return "ESTADO_NO_CONFIRMADO", (
            f"Timeout de {timeout_seconds}s sin evidencia suficiente"
        )

    def _completion_evidence(self, inspection: Inspection) -> bool:
        if self.driver is None:
            return False
        lower = inspection.inspected_text.lower()
        terms = (
            "execution completed",
            "ejecución completada",
            "ejecucion completada",
            "robot finalizado",
            "finished successfully",
            "finalizado correctamente",
        )
        return any(term in lower for term in terms)

    def close(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
