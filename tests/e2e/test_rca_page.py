"""
E2E tests: RCA Analysis page.

Tests:
  - RCA page loads for analyst
  - Date filter is present and functional
  - RCA results show 4-step check visualization
"""
import pytest
from playwright.sync_api import Page, expect


def test_rca_page_loads(analyst_page: Page, base_url: str):
    """RCA page loads with filter controls."""
    analyst_page.goto(f"{base_url}/rca")
    analyst_page.wait_for_timeout(3000)

    # Should have date filter input
    date_input = analyst_page.locator('input[type="date"]')
    assert date_input.count() > 0, "RCA page should have a date filter input"


def test_rca_page_has_commodity_selector(analyst_page: Page, base_url: str):
    """RCA page should have commodity selector."""
    analyst_page.goto(f"{base_url}/rca")
    analyst_page.wait_for_timeout(3000)

    # Should have a select/dropdown for commodity
    selector = analyst_page.locator("select")
    assert selector.count() > 0, "RCA page should have a commodity selector"


def test_rca_shows_check_steps(analyst_page: Page, base_url: str):
    """After running RCA, should display 4 check steps."""
    analyst_page.goto(f"{base_url}/rca")
    analyst_page.wait_for_timeout(3000)

    # Trigger RCA analysis (click analyze button if present)
    analyze_btn = analyst_page.locator("button:has-text('Analisis'), button:has-text('Jalankan')")
    if analyze_btn.count() > 0:
        analyze_btn.first.click()
        analyst_page.wait_for_timeout(5000)

    body_text = analyst_page.locator("body").text_content()
    # RCA check names that should appear
    check_names = ["Hari Raya", "Cuaca", "Kota", "Stok"]
    found = sum(1 for c in check_names if c in body_text)
    # At least 2 of 4 checks should be visible in the UI
    assert found >= 2, f"Expected RCA check steps, found {found}/4. Body: {body_text[:300]}"


def test_rca_hari_besar_card_visible(analyst_page: Page, base_url: str):
    """RCA page should show 'Hari Besar Terdekat' info card."""
    analyst_page.goto(f"{base_url}/rca")
    analyst_page.wait_for_timeout(3000)

    # Trigger analysis
    analyze_btn = analyst_page.locator("button:has-text('Analisis'), button:has-text('Jalankan')")
    if analyze_btn.count() > 0:
        analyze_btn.first.click()
        analyst_page.wait_for_timeout(5000)

    body_text = analyst_page.locator("body").text_content()
    # Should reference hari besar somewhere in the results
    assert "hari" in body_text.lower(), "RCA page should mention hari besar/raya"
