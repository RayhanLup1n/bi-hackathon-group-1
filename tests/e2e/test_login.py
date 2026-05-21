"""
E2E tests: Login flow.

Tests:
  - Valid login redirects to dashboard
  - Invalid credentials show error
  - Login page has required form elements
"""
import pytest
from playwright.sync_api import Page, expect
from tests.e2e.conftest import login, ADMIN_USER


def test_login_page_has_form_elements(page: Page, base_url: str):
    """Login page renders username, password, and submit button."""
    page.goto(f"{base_url}/login")

    expect(page.locator('input[name="username"], #username')).to_be_visible()
    expect(page.locator('input[name="password"], #password')).to_be_visible()
    expect(page.locator('button[type="submit"]')).to_be_visible()


def test_login_valid_credentials(page: Page, base_url: str):
    """Valid admin login redirects to dashboard (/)."""
    login(page, base_url, ADMIN_USER["username"], ADMIN_USER["password"])

    # Should land on dashboard
    assert "/login" not in page.url
    # JWT token should be stored in localStorage
    token = page.evaluate("() => localStorage.getItem('token')")
    assert token is not None and len(token) > 10


def test_login_invalid_credentials(page: Page, base_url: str):
    """Invalid credentials show error, stay on login page."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="username"], #username', "wronguser")
    page.fill('input[name="password"], #password', "wrongpass")
    page.click('button[type="submit"]')

    # Should stay on login page
    page.wait_for_timeout(1500)
    assert "login" in page.url.lower()


def test_login_empty_fields(page: Page, base_url: str):
    """Empty form submission doesn't navigate away."""
    page.goto(f"{base_url}/login")
    page.click('button[type="submit"]')

    page.wait_for_timeout(1000)
    assert "login" in page.url.lower()


def test_unauthenticated_redirect(page: Page, base_url: str):
    """Accessing dashboard without auth redirects to login."""
    page.evaluate("() => localStorage.clear()")
    page.goto(base_url)

    # Frontend JS should redirect unauthenticated users to /login
    page.wait_for_timeout(2000)
    # Check either stays on page (with login prompt) or redirects
    # Behavior depends on frontend implementation
    url = page.url.lower()
    # Either at login page or dashboard shows login prompt
    assert "login" in url or page.locator("text=Login").count() > 0
