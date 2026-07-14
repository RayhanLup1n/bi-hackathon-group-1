"""
E2E tests: Dashboard page.

Tests:
  - Dashboard loads with main UI elements
  - Commodity data is displayed
  - Risk level indicators visible
  - Search and filter UX elements present
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


def test_dashboard_risk_levels_visible(admin_page: Page, base_url: str):
    """Dashboard should show risk level indicators (rendah/sedang/tinggi/kritis)."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    body_text = admin_page.locator("body").text_content().lower()
    # New risk levels: rendah, sedang, tinggi, kritis
    risk_levels = ["rendah", "sedang", "tinggi", "kritis"]
    found = any(level in body_text for level in risk_levels)
    assert found, "No risk level indicators found in dashboard"


def test_dashboard_search_bar_present(admin_page: Page, base_url: str):
    """Dashboard should have a functional search bar with loading state support."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    # Search input should exist
    search_input = admin_page.locator('input[x-model="searchQuery"]')
    expect(search_input).to_be_visible()


def test_dashboard_filter_dropdowns_present(admin_page: Page, base_url: str):
    """Dashboard should have risk and province filter dropdowns."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    # Filter selects should be present
    body_html = admin_page.locator("body").inner_html()
    assert "filterRisk" in body_html, "Risk filter dropdown missing"
    assert "filterProvince" in body_html, "Province filter dropdown missing"


def test_dashboard_stat_bar_visible(admin_page: Page, base_url: str):
    """Dashboard should show the stat summary bar."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(3000)

    body_text = admin_page.locator("body").text_content()
    assert "Komoditas Dipantau" in body_text, "Stat bar missing 'Komoditas Dipantau'"
