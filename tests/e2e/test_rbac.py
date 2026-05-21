"""
E2E tests: RBAC enforcement.

Tests:
  - Admin can access /admin, analyst cannot
  - Analyst can access /rca and /prediksi
  - Navigation links match user role
"""
import pytest
from playwright.sync_api import Page, expect
from tests.e2e.conftest import login, ADMIN_USER, ANALYST_USER


def test_admin_can_access_admin_page(admin_page: Page, base_url: str):
    """Admin user can navigate to /admin page."""
    admin_page.goto(f"{base_url}/admin")
    admin_page.wait_for_timeout(2000)

    # Should NOT be redirected away
    assert "admin" in admin_page.url.lower()


def test_analyst_cannot_access_admin_page(analyst_page: Page, base_url: str):
    """Analyst should be redirected away from /admin."""
    analyst_page.goto(f"{base_url}/admin")
    analyst_page.wait_for_timeout(2000)

    # Should be redirected (to dashboard or login)
    url = analyst_page.url.lower()
    assert "admin" not in url or analyst_page.locator("text=Akses ditolak").count() > 0


def test_analyst_can_access_rca(analyst_page: Page, base_url: str):
    """Analyst can access /rca page."""
    analyst_page.goto(f"{base_url}/rca")
    analyst_page.wait_for_timeout(2000)

    assert "rca" in analyst_page.url.lower()


def test_analyst_can_access_prediksi(analyst_page: Page, base_url: str):
    """Analyst can access /prediksi page."""
    analyst_page.goto(f"{base_url}/prediksi")
    analyst_page.wait_for_timeout(2000)

    assert "prediksi" in analyst_page.url.lower()


def test_admin_nav_shows_all_links(admin_page: Page, base_url: str):
    """Admin should see nav links for Dashboard, RCA, Prediksi, Admin."""
    admin_page.goto(base_url)
    admin_page.wait_for_timeout(2000)

    # Check for navigation links
    nav = admin_page.locator("nav, .nav, header")
    if nav.count() > 0:
        nav_text = nav.first.text_content()
        assert "Admin" in nav_text or admin_page.locator('a[href="/admin"]').count() > 0


def test_analyst_nav_hides_admin_link(analyst_page: Page, base_url: str):
    """Analyst should NOT see Admin nav link."""
    analyst_page.goto(base_url)
    analyst_page.wait_for_timeout(2000)

    # Admin link should not be visible
    admin_link = analyst_page.locator('a[href="/admin"]')
    if admin_link.count() > 0:
        expect(admin_link.first).not_to_be_visible()
