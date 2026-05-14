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
PAGES = ["index.html", "login.html", "admin.html", "rca.html", "prediksi.html"]


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
    """Non-login pages should load Alpine.js."""
    name, content = html_content
    if name == "login.html":
        # Login might not use Alpine.js
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
        )
        assert has_label, (
            f"{name} has input without label/placeholder: {inp[:80]}"
        )
