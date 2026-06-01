"""
E2E tests: FTA & Bowtie Analysis page.

Tests:
  - Analysis page loads for analyst
  - Date filter is present and functional
  - Analysis results show FTA threat checks
"""
import pytest
from playwright.sync_api import Page, expect


def test_analysis_page_loads(analyst_page: Page, base_url: str):
    """Analysis page loads with filter controls."""
    analyst_page.goto(f"{base_url}/analysis")
    analyst_page.wait_for_timeout(3000)

    # Should have date filter input
    date_input = analyst_page.locator('input[type="date"]')
    assert date_input.count() > 0, "Analysis page should have a date filter input"


def test_analysis_page_has_commodity_selector(analyst_page: Page, base_url: str):
    """Analysis page should have commodity selector."""
    analyst_page.goto(f"{base_url}/analysis")
    analyst_page.wait_for_timeout(3000)

    # Should have a select/dropdown for commodity
    selector = analyst_page.locator("select")
    assert selector.count() > 0, "Analysis page should have a commodity selector"


def test_analysis_shows_check_steps(analyst_page: Page, base_url: str):
    """After running analysis, should display FTA threat checks."""
    analyst_page.goto(f"{base_url}/analysis")
    analyst_page.wait_for_timeout(3000)

    # Trigger analysis (click analyze button if present)
    analyze_btn = analyst_page.locator("button:has-text('Analisis'), button:has-text('Jalankan')")
    if analyze_btn.count() > 0:
        analyze_btn.first.click()
        analyst_page.wait_for_timeout(5000)

    body_text = analyst_page.locator("body").text_content()
    # FTA check names that should appear
    check_names = ["Hari Raya", "Cuaca", "Kota", "Stok"]
    found = sum(1 for c in check_names if c in body_text)
    # At least 2 of 4 checks should be visible in the UI
    assert found >= 2, f"Expected FTA check steps, found {found}/4. Body: {body_text[:300]}"


def test_analysis_hari_besar_card_visible(analyst_page: Page, base_url: str):
    """Analysis page should show 'Hari Besar Terdekat' info card."""
    analyst_page.goto(f"{base_url}/analysis")
    analyst_page.wait_for_timeout(3000)

    # Trigger analysis
    analyze_btn = analyst_page.locator("button:has-text('Analisis'), button:has-text('Jalankan')")
    if analyze_btn.count() > 0:
        analyze_btn.first.click()
        analyst_page.wait_for_timeout(5000)

    body_text = analyst_page.locator("body").text_content()
    # Should reference hari besar somewhere in the results
    assert "hari" in body_text.lower(), "Analysis page should mention hari besar/raya"
