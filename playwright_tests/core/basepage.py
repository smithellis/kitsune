import random
from typing import Union
from playwright.sync_api import Page, ElementHandle, Locator
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class BasePage:

    def __init__(self, page: Page):
        self.page = page

    def _get_element_locator(self, xpath: str, with_wait=True) -> Locator:
        """
        This helper function returns the element locator from a given xpath.
        """
        if with_wait:
            self.wait_for_dom_to_load()
        return self.page.locator(xpath)

    def _get_elements_locators(self, xpath: str) -> list[Locator]:
        """
        This helper function returns a list of element locators from a given xpath.
        """
        self.wait_for_dom_to_load()
        return self.page.locator(xpath).all()

    def _get_current_page_url(self) -> str:
        """
        This helper function returns the current page URL.
        """
        return self.page.url

    def _get_element_handles(self, xpath: str) -> list[ElementHandle]:
        """
        This helper function returns a list of element handles from a given xpath.
        """
        return self._get_element_locator(xpath).element_handles()

    def _get_element_handle(self, xpath: str) -> ElementHandle:
        """
        This helper function returns a single element handle from a given xpath.
        """
        return self._get_element_locator(xpath).element_handle()

    def _get_text_of_elements(self, xpath: str) -> list[str]:
        """
        This helper function returns a list containing the inner texts of a given xpath.
        """
        return self._get_element_locator(xpath).all_inner_texts()

    def _get_text_of_element(self, xpath: str) -> str:
        """
        This helper function returns the inner text of a given xpath.
        """
        return self._get_element_locator(xpath).inner_text()

    def _get_text_of_locator(self, locator: Locator) -> str:
        """
        This helper function returns the inner text of a given locator.
        """
        return locator.inner_text()

    def _is_element_empty(self, xpath: str) -> bool:
        """
        This helper function returns checks if the given xpath has an inner text.
        """
        return not self._get_element_locator(xpath).inner_text()

    def _get_elements_count(self, xpath: str) -> int:
        """
        This helper function returns the web element count from a given xpath.
        """
        return self._get_element_locator(xpath).count()

    def _get_element_attribute_value(self, element: Union[str, Locator, list[Locator],
                                     ElementHandle], attribute: str) -> Union[str, list[str]]:
        """
        This helper function returns the given attribute of a given locator or web element.
        """
        if isinstance(element, str):
            return self._get_element_locator(element).get_attribute(attribute)
        elif isinstance(element, list):
            self.wait_for_dom_to_load()
            values = []
            for element in element:
                values.append(element.get_attribute(attribute))
            return values
        else:
            return element.get_attribute(attribute)

    def _wait_for_given_timeout(self, timeout: float):
        """
        This helper function pauses the execution for a given timeout.
        """
        self.page.wait_for_timeout(timeout)

    def _get_element_input_value(self, xpath: str) -> str:
        """
        This helper function returns the input value of a given element locator.
        """
        return self._get_element_locator(xpath).input_value()

    def _get_element_inner_text_from_page(self, xpath: str) -> str:
        """
        This helper function returns the inner text of a given locator via the page instance.
        """
        return self.page.inner_text(xpath)

    def _get_element_text_content(self, xpath: str) -> str:
        """
        This helper function returns the text content of a given locator via the page instance.
        """
        return self.page.text_content(xpath)

    def _get_text_content_of_all_locators(self, locator: Locator) -> list[str]:
        """
        This helper function returns a list of text content for the given locator.
        """
        return locator.all_text_contents()

    def _checkbox_interaction(self, element: [str, ElementHandle], check: bool, retries=3,
                              delay=2000):
        """
        This helper function interacts with a checkbox element.

        Args:
        element (Union[str, ElementHandle]): The element locator to interact with.
        check (bool): Whether to check or uncheck the checkbox.
        """
        self.wait_for_networkidle()
        for attempt in range(retries):
            try:
                locator = self._get_element_locator(element) if isinstance(
                    element,str) else element
                if check:
                    locator.check()
                else:
                    locator.uncheck()
                break
            except (PlaywrightTimeoutError, Exception) as e:
                print(f"Checkbox interaction failed. Retrying... {e}")
                if attempt < retries - 1:
                    self.page.wait_for_timeout(delay)
                else:
                    raise Exception("Max retries exceeded. Could not interact with the checkbox")

    def _click(self, element: Union[str, Locator, ElementHandle], expected_locator=None,
               expected_url=None, with_force=False, retries=3, delay=2000):
        """
        This helper function clicks on a given element locator.

        Args:
        element (Union[str, Locator, ElementHandle]): The element locator to click on.
        expected_locator (str): The expected locator to wait for after the click.
        expected_url (str): The expected URL to wait for after the click.
        with_force (bool): Whether to force the click.
        """
        self.wait_for_networkidle()
        for attempt in range(retries):
            try:
                element_locator = self._get_element_locator(element) if isinstance(
                    element, str) else element
                element_locator.click(force=with_force)
                if expected_locator:
                    self.page.wait_for_selector(expected_locator, timeout=3000)
                if expected_url:
                    self.page.wait_for_url(expected_url, timeout=3000)
                break
            except PlaywrightTimeoutError:
                if expected_locator:
                    print(f"Expected locator {expected_locator} not found. Retrying...")
                if expected_url:
                    print(f"Expected URL {expected_url} not found. Retrying...")
                if attempt < retries - 1:
                    self.page.wait_for_timeout(delay)

    def _click_on_an_element_by_index(self, xpath: str, index: int):
        """
        This helper function clicks on a given element locator based on a given index.
        """
        self.wait_for_networkidle()
        self._get_element_locator(xpath).nth(index).click()

    def _click_on_first_item(self, xpath: str):
        """
        This helper function clicks on the first item from a given web element locator list.
        """
        self.wait_for_networkidle()
        self._get_element_locator(xpath).first.click()

    def _fill(self, xpath: str, text: str):
        """
        This helper function fills a given text inside a given element locator.
        """
        self._get_element_locator(xpath).fill(text)

    def _type(self, xpath: str, text: str, delay: int):
        """
        This helper function types a given string inside a given element locator with a given delay
        """
        self._get_element_locator(xpath).type(text=text, delay=delay)

    def _press_a_key(self, xpath: str, key: str):
        """
        This helper function types a given key inside a given element locator.
        """
        self._get_element_locator(xpath).press(key)

    def _clear_field(self, xpath: str):
        """
        This helper function clears the given element locator input field.
        """
        self._get_element_locator(xpath).clear()

    def _select_option_by_label(self, xpath: str, label_name: str):
        """
        This helper function selects an element from a given select box based on label.
        """
        self._get_element_locator(xpath).select_option(label=label_name)

    def _select_option_by_value(self, xpath: str, value: str):
        """
        This helper function selects a element from a given select box based on value.
        """
        self._get_element_locator(xpath).select_option(value=value)

    def _select_random_option_by_value(self, dropdown_locator: str, xpath_options: str):
        """
        This helper function selects a random option from a given web element locator.
        """
        elements = []
        for element in self._get_elements_locators(xpath_options):
            locator_value = self._get_element_attribute_value(element, 'value')
            if locator_value == '':
                continue
            else:
                elements.append(locator_value)
        self._select_option_by_value(dropdown_locator, random.choice(elements))

    def _accept_dialog(self):
        """
        This helper function accepts the displayed dialog.
        """
        self.page.on("dialog", lambda dialog: dialog.accept())

    def _hover_over_element(self, xpath: str):
        """
        This helper function performs a mouse-over action over a given element locator.
        """
        self._get_element_locator(xpath).hover()

    def _is_element_visible(self, xpath: str) -> bool:
        """
        This helper function finds the locator of the given xpath and checks if it is visible.
        """
        return self._get_element_locator(xpath).is_visible()

    def _is_locator_visible(self, locator: Locator) -> bool:
        """
        This helper function checks if the given locator is visible.
        """
        return locator.is_visible()

    def _is_checkbox_checked(self, xpath: str) -> bool:
        """
        This helper function checks if a given element locator is checked.
        """
        return self._get_element_locator(xpath).is_checked()

    def _wait_for_selector(self, xpath: str, timeout=3500):
        """
        This helper function waits for a given element locator to be visible based on a given
        timeout.
        """
        try:
            self.page.wait_for_selector(xpath, timeout=timeout)
        except PlaywrightTimeoutError:
            print(f"{xpath} is not displayed")

    def _move_mouse_to_location(self, x: int, y: int):
        """
        This helper function moves the mouse to a given location.

        Args:
        x (int): The x-coordinate.
        y (int): The y-coordinate.
        """
        self.page.mouse.move(x, y)

    def wait_for_page_to_load(self):
        """
        This helper function awaits for the load event to be fired.
        """
        try:
            self.page.wait_for_load_state("load")
        except PlaywrightTimeoutError:
            print("Load event was not fired. Continuing...")

    def wait_for_dom_to_load(self):
        """
        This helper function awaits for the DOMContentLoaded event to be fired.
        """
        try:
            self.page.wait_for_load_state("domcontentloaded")
        except PlaywrightTimeoutError:
            print("DOMContentLoaded event was not fired. Continuing...")

    def wait_for_networkidle(self):
        """
        This helper function waits until there are no network connections for at least 500ms.
        """
        try:
            self.page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            print("Network idle state was not reached. Continuing...")
