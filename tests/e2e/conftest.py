"""
Shared fixtures for E2E (Playwright) tests.

Usage:
  uv run pytest tests/e2e/ --headed   # watch in browser
  uv run pytest tests/e2e/            # headless (CI)

Prerequisites:
  uv add --dev pytest-playwright
  playwright install chromium
"""
import os
import pytest
from playwright.sync_api import Page, BrowserContext

# Base URL — override with E2E_BASE_URL env var
BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")

# Test credentials (must match seeded users in app.users)
ADMIN_USER = {"username": "admin", "password": "admin123"}
ANALYST_USER = {"username": "analyst", "password": "analyst123"}


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture
def page(context: BrowserContext, base_url: str) -> Page:
    """Fresh page for each test — clears localStorage."""
    pg = context.new_page()
    pg.goto(base_url)
    pg.evaluate("() => localStorage.clear()")
    yield pg
    pg.close()


def login(page: Page, base_url: str, username: str, password: str) -> None:
    """Helper: perform login via the login page."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="username"], #username', username)
    page.fill('input[name="password"], #password', password)
    page.click('button[type="submit"]')
    # Wait for redirect away from /login
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)


@pytest.fixture
def admin_page(context: BrowserContext, base_url: str) -> Page:
    """Page logged in as admin."""
    pg = context.new_page()
    login(pg, base_url, ADMIN_USER["username"], ADMIN_USER["password"])
    yield pg
    pg.close()


@pytest.fixture
def analyst_page(context: BrowserContext, base_url: str) -> Page:
    """Page logged in as analyst."""
    pg = context.new_page()
    login(pg, base_url, ANALYST_USER["username"], ANALYST_USER["password"])
    yield pg
    pg.close()
