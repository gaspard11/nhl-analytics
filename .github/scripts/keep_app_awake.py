"""Opens every page of the Streamlit app in a headless browser.

Streamlit Community Cloud puts an app to sleep after 12 hours without a visit, and a plain HTTP
request doesn't count as one: the page has to be rendered by a browser. Visiting every page also
fills the app's cache with the day's queries before the first real visitor.

Run by .github/workflows/keep-app-awake.yml. The app URL comes from the APP_URL environment variable.
"""

import os
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


APP_URL = os.environ["APP_URL"].rstrip("/")
# URL paths of the pages, from their file names in app/app.py ("" is the default page, Games)
PAGES = ["", "standings", "evolution", "player_stats"]

WAKE_UP_BUTTON = "Yes, get this app back up!"
APP_IFRAME = 'iframe[title="streamlitApp"]'  # on *.streamlit.app the app runs inside this iframe
BOOT_TIMEOUT_MS = 300_000  # a sleeping app can take a few minutes to start again
PAGE_TIMEOUT_MS = 120_000


def wake_up_if_asleep(page):
    """A sleeping app shows a wake-up button instead of the app."""
    page.wait_for_selector(f'{APP_IFRAME}, button:has-text("{WAKE_UP_BUTTON}")', timeout=PAGE_TIMEOUT_MS)
    wake_up = page.get_by_role("button", name=WAKE_UP_BUTTON)
    if wake_up.count():
        print("App was asleep, waking it up")
        wake_up.click()
        page.wait_for_selector(APP_IFRAME, timeout=BOOT_TIMEOUT_MS)


def wait_until_rendered(page):
    """Waits for the page's script to finish, and fails if it raised an error."""
    app = page.frame_locator(APP_IFRAME)
    app.locator('[data-testid="stApp"]').wait_for(timeout=BOOT_TIMEOUT_MS)
    page.wait_for_timeout(5_000)  # lets the script start, so the spinner below exists if a query runs
    # "Loading data..." is shown while a query runs: hidden means the data is loaded (or was cached)
    app.locator('[data-testid="stSpinner"]').first.wait_for(state="hidden", timeout=PAGE_TIMEOUT_MS)
    if app.locator('[data-testid="stException"]').count():
        raise RuntimeError("the page shows an error")


def main():
    failed = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        for path in PAGES:
            url = f"{APP_URL}/{path}"
            try:
                page.goto(url, timeout=PAGE_TIMEOUT_MS)
                wake_up_if_asleep(page)
                wait_until_rendered(page)
                print(f"OK      {url}")
            except (PlaywrightTimeout, RuntimeError) as error:
                print(f"FAILED  {url}: {error}")
                failed.append(url)
        browser.close()

    # A failed run shows up red in GitHub Actions, and GitHub emails the repo owner
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
