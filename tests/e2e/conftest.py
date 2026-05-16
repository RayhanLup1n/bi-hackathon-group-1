"""
Shared fixtures for E2E (Playwright) tests.

Usage:
  uv run pytest tests/e2e/ --headed   # watch in browser
  uv run pytest tests/e2e/            # headless (CI)

Prerequisites:
  uv add --dev pytest-playwright
  playwright install chromium

Notes:
  - test_html_structure.py does NOT need playwright (pure file reading)
  - All other test files require playwright - they will be skipped if not installed
"""
import os
import pytest

try:
    from playwright.sync_api import Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    # Playwright is optional - HTML structure tests don't need it
    Page = None
    BrowserContext = None
    HAS_PLAYWRIGHT = False

# Base URL - override with E2E_BASE_URL env var
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")

# Test credentials (must match seeded users in app.users)
ADMIN_USER = {"username": "admin", "password": "admin123"}
ANALYST_USER = {"username": "analyst", "password": "analyst123"}


def pytest_collect_file(parent, file_path):
    """Skip test files that need playwright when it's not installed."""
    if not HAS_PLAYWRIGHT and file_path.name.startswith("test_") and file_path.name != "test_html_structure.py":
        return None
    return None  # let default collection handle it


def pytest_ignore_collect(collection_path, config):
    """Ignore playwright-dependent test files when playwright is not installed."""
    if not HAS_PLAYWRIGHT:
        name = collection_path.name
        playwright_tests = [
            "test_login.py",
            "test_rbac.py",
            "test_dashboard.py",
            "test_rca_page.py",
            "test_navigation.py",
            "test_responsive.py",
        ]
        if name in playwright_tests:
            return True
    return False


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def page(context, base_url: str):
    """Fresh page for each test - clears localStorage."""
    if not HAS_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    pg = context.new_page()
    pg.goto(base_url)
    pg.evaluate("() => localStorage.clear()")
    yield pg
    pg.close()


def login(page, base_url: str, username: str, password: str) -> None:
    """Helper: perform login via the login page."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="username"], #username', username)
    page.fill('input[name="password"], #password', password)
    page.click('button[type="submit"]')
    # Wait for redirect away from /login
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)


@pytest.fixture
def admin_page(context, base_url: str):
    """Page logged in as admin."""
    if not HAS_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    pg = context.new_page()
    login(pg, base_url, ADMIN_USER["username"], ADMIN_USER["password"])
    yield pg
    pg.close()


@pytest.fixture
def analyst_page(context, base_url: str):
    """Page logged in as analyst."""
    if not HAS_PLAYWRIGHT:
        pytest.skip("playwright not installed")
    pg = context.new_page()
    login(pg, base_url, ANALYST_USER["username"], ANALYST_USER["password"])
    yield pg
    pg.close()
