"""
HTML structure validation tests (no server needed).

Validates frontend HTML files directly for:
  - Required meta tags
  - Accessibility basics (alt attributes, form labels)
  - Alpine.js directives present
  - Consistent nav structure across pages
"""
import os
import re
import pytest

FRONTEND_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend"
)

# All pages that should exist
PAGES = ["index.html", "login.html", "admin.html", "rca.html", "prediksi.html", "guide.html"]


@pytest.fixture(params=PAGES)
def html_content(request) -> tuple[str, str]:
    """Read each frontend HTML file. Returns (filename, content)."""
    path = os.path.join(FRONTEND_DIR, request.param)
    if not os.path.exists(path):
        pytest.skip(f"{request.param} does not exist")
    with open(path, encoding="utf-8") as f:
        return request.param, f.read()


def test_has_doctype(html_content):
    """Every page should start with <!DOCTYPE html>."""
    name, content = html_content
    assert content.strip().lower().startswith("<!doctype html"), (
        f"{name} missing <!DOCTYPE html>"
    )


def test_has_charset_meta(html_content):
    """Every page should declare UTF-8 charset."""
    name, content = html_content
    assert 'charset="utf-8"' in content.lower() or "charset=utf-8" in content.lower(), (
        f"{name} missing charset=utf-8 meta tag"
    )


def test_has_viewport_meta(html_content):
    """Every page should have viewport meta for responsiveness."""
    name, content = html_content
    assert "viewport" in content.lower(), (
        f"{name} missing viewport meta tag"
    )


def test_has_title(html_content):
    """Every page should have a <title> tag."""
    name, content = html_content
    assert "<title>" in content.lower() and "</title>" in content.lower(), (
        f"{name} missing <title> tag"
    )


def test_has_lang_attribute(html_content):
    """Every page should have lang attribute on <html>."""
    name, content = html_content
    # Accept lang="id" or lang="en" or similar
    assert re.search(r'<html[^>]*\slang=', content, re.IGNORECASE), (
        f"{name} missing lang attribute on <html> tag"
    )


def test_alpine_js_loaded(html_content):
    """Pages using Alpine.js should load it."""
    name, content = html_content
    if name in ("login.html", "guide.html", "admin.html"):
        # Login, guide, and admin pages use vanilla JS, not Alpine.js
        return
    # Check for Alpine.js CDN or local script
    has_alpine = "alpine" in content.lower()
    assert has_alpine, f"{name} does not reference Alpine.js"


def test_no_inline_credentials(html_content):
    """No hardcoded passwords or API keys in HTML."""
    name, content = html_content
    # Patterns that should NOT appear
    bad_patterns = [
        r'password\s*[:=]\s*["\'][^"\']+["\']',  # password: "xxx"
        r'api[_-]?key\s*[:=]\s*["\'][^"\']+["\']',  # api_key: "xxx"
        r'secret\s*[:=]\s*["\'][^"\']+["\']',  # secret: "xxx"
    ]
    for pattern in bad_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        # Filter out false positives (input type="password", placeholder text)
        real_matches = [
            m for m in matches
            if 'type=' not in m.lower()
            and 'placeholder' not in m.lower()
            and 'label' not in m.lower()
        ]
        assert not real_matches, (
            f"{name} may contain hardcoded credentials: {real_matches}"
        )


def test_forms_have_labels_or_placeholders(html_content):
    """Form inputs should have associated labels or placeholder text."""
    name, content = html_content
    # Find all <input> tags (excluding hidden, submit, button types)
    inputs = re.findall(
        r'<input[^>]*type=["\'](?:text|password|email|date|number)["\'][^>]*>',
        content,
        re.IGNORECASE,
    )
    for inp in inputs:
        has_label = (
            "placeholder=" in inp.lower()
            or "aria-label=" in inp.lower()
            or "id=" in inp.lower()  # likely has an associated <label for="...">
            or "x-model" in inp.lower()  # Alpine.js binding acts as identifier
        )
        assert has_label, (
            f"{name} has input without label/placeholder: {inp[:80]}"
        )


# ── Dashboard-specific structure tests ──────────────────────────────────────


def _read_page(filename: str) -> str:
    """Read a single frontend page."""
    path = os.path.join(FRONTEND_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestDashboardStructure:
    """Tests specific to the Executive Dashboard (index.html) revamp layout."""

    def test_has_executive_dashboard_component(self):
        """Dashboard should use the Executive Dashboard Alpine component."""
        content = _read_page("index.html")
        assert "executiveDashboard" in content
        assert "loadOverview" in content

    def test_has_priority_cards(self):
        """Dashboard should show priority cards with risk levels."""
        content = _read_page("index.html")
        assert "priority-card" in content
        assert "risk-kritis" in content
        assert "priority-name" in content

    def test_has_top_stat_bar(self):
        """Dashboard should show top stat bar with summary counts."""
        content = _read_page("index.html")
        assert "dash-stat" in content
        assert "Komoditas Dipantau" in content

    def test_has_freshness_indicator(self):
        """Dashboard should show data freshness bar."""
        content = _read_page("index.html")
        assert "freshness-bar" in content
        assert "freshness-dot" in content

    def test_has_ml_offline_warning(self):
        """Dashboard should handle ML offline gracefully."""
        content = _read_page("index.html")
        assert "ml-service" in content.lower() or "ml_service" in content
        assert "offline" in content.lower()

    def test_has_review_bundle_section(self):
        """Dashboard should have review bundle section."""
        content = _read_page("index.html")
        assert "review_bundles" in content
        assert "Paket Tinjauan" in content

    def test_has_detail_view(self):
        """Dashboard should support detail view routing."""
        content = _read_page("index.html")
        assert "openDetail" in content
        assert "detailLoading" in content

    def test_has_evidence_groups(self):
        """Detail view should separate evidence into groups."""
        content = _read_page("index.html")
        assert "evidence-block" in content
        assert "Fakta Teramati" in content
        assert "Output Model" in content

    def test_has_human_review_buttons(self):
        """Detail view should have human review action buttons."""
        content = _read_page("index.html")
        assert "Untuk Dibahas" in content
        assert "Ditunda" in content
        assert "Ditolak" in content
        assert "submitReview" in content

    def test_has_response_options(self):
        """Dashboard should show response options from rule engine."""
        content = _read_page("index.html")
        assert "response_options" in content
        assert "response-option" in content

    def test_has_missing_information_section(self):
        """Detail view should show missing information block."""
        content = _read_page("index.html")
        assert "missing_information" in content
        assert "Belum Tersedia" in content

    def test_tagline_updated(self):
        """Dashboard header should show decision-support tagline."""
        content = _read_page("index.html")
        assert "decision-support" in content.lower()

    def test_chart_in_detail_view(self):
        """Detail view should have price history chart."""
        content = _read_page("index.html")
        assert "detailPriceChart" in content
        assert "buildDetailChart" in content

    def test_graceful_ml_offline(self):
        """Dashboard should handle ML server offline with banner."""
        content = _read_page("index.html")
        assert "ML service offline" in content or "ml offline" in content.lower()


class TestFTAPageStructure:
    """Tests specific to the FTA/Analysis page (rca.html)."""

    def test_has_bowtie_section(self):
        content = _read_page("rca.html")
        assert "bowtieData" in content
        assert "Bowtie" in content

    def test_has_fta_threats(self):
        content = _read_page("rca.html")
        assert "FTA" in content
        assert "active_threats" in content

    def test_has_analysis_checklist(self):
        content = _read_page("rca.html")
        assert "Hari Raya" in content
        assert "Cuaca" in content


class TestPrediksiPageStructure:
    """Tests specific to the Prediksi page (prediksi.html)."""

    def test_has_ml_source_toggle(self):
        content = _read_page("prediksi.html")
        assert "source" in content
        # Should support both ML and DB sources
        assert "ml" in content.lower()

    def test_has_prediction_display(self):
        content = _read_page("prediksi.html")
        assert "prediksi" in content.lower() or "prediction" in content.lower()
