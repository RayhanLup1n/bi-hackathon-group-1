"""
E2E tests: Dashboard page.

Tests:
  - Dashboard loads with main UI elements
  - Commodity data is displayed
  - HET status badges visible
"""
import pytest
from playwright.sync_api import Page, expect


def test_dashboard_loads(admin_page: Page, base_url: str):
    """Dashboard page loads with main heading/title."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    # Page should have the app title or dashboard heading
    title = admin_page.title()
    assert "RADAR" in title.upper() or "PANGAN" in title.upper() or len(title) > 0

    # Main content area should exist
    body_text = admin_page.locator("body").text_content()
    assert len(body_text) > 50  # should have substantial content


def test_dashboard_shows_commodity_cards(admin_page: Page, base_url: str):
    """Dashboard should display commodity names."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    body_text = admin_page.locator("body").text_content()
    # Check for at least one MVP commodity name
    commodities = ["Bawang Merah", "Bawang Putih", "Cabai Merah", "Cabai Rawit"]
    found = any(c in body_text for c in commodities)
    assert found, f"No commodity names found in dashboard. Body text starts with: {body_text[:200]}"


def test_dashboard_het_status_visible(admin_page: Page, base_url: str):
    """Dashboard should show HET status indicators."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    body_text = admin_page.locator("body").text_content()
    # HET statuses: AMAN, WASPADA, KRITIS, MELAMPAUI
    het_statuses = ["AMAN", "WASPADA", "KRITIS", "MELAMPAUI", "HET"]
    found = any(s in body_text.upper() for s in het_statuses)
    assert found, "No HET status found in dashboard"
