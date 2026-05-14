"""
E2E tests: Responsive design.

Tests:
  - Pages render correctly on mobile viewport
  - No horizontal overflow on small screens
"""
import pytest
from playwright.sync_api import Page, BrowserContext


@pytest.fixture
def mobile_page(context: BrowserContext, base_url: str) -> Page:
    """Page with mobile viewport (375x812 — iPhone X)."""
    pg = context.new_page()
    pg.set_viewport_size({"width": 375, "height": 812})
    yield pg
    pg.close()


def test_login_page_mobile(mobile_page: Page, base_url: str):
    """Login page should render without horizontal scroll on mobile."""
    mobile_page.goto(f"{base_url}/login")
    mobile_page.wait_for_timeout(2000)

    # Check no horizontal overflow
    has_overflow = mobile_page.evaluate("""
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    """)
    assert not has_overflow, "Login page has horizontal overflow on mobile"


def test_dashboard_mobile(mobile_page: Page, base_url: str):
    """Dashboard should be usable on mobile viewport."""
    # Login first
    from tests.e2e.conftest import login, ADMIN_USER
    login(mobile_page, base_url, ADMIN_USER["username"], ADMIN_USER["password"])

    mobile_page.goto(base_url)
    mobile_page.wait_for_timeout(3000)

    # Check no horizontal overflow
    has_overflow = mobile_page.evaluate("""
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    """)
    assert not has_overflow, "Dashboard has horizontal overflow on mobile"

    # Body should have content
    body_text = mobile_page.locator("body").text_content()
    assert len(body_text) > 50
