import os
import pytest
from ui.asset_loader import get_assets_dir, get_asset_path, read_asset_text, get_assets_base_url

def test_assets_exist():
    assets_dir = get_assets_dir()
    assert os.path.isdir(assets_dir)
    
    marked_path = get_asset_path("marked.min.js")
    purify_path = get_asset_path("purify.min.js")
    mathjax_path = get_asset_path("tex-mml-chtml.js")
    
    assert os.path.exists(marked_path)
    assert os.path.exists(purify_path)
    assert os.path.exists(mathjax_path)

def test_read_asset_text():
    content = read_asset_text("marked.min.js")
    assert len(content) > 1000
    assert "marked" in content.lower()

def test_assets_base_url():
    url = get_assets_base_url()
    assert url.isLocalFile()
    assert os.path.exists(url.toLocalFile())

def test_chat_html_template_has_local_scripts():
    from ui.ai_chat_panel import AIChatPanel
    panel = AIChatPanel()
    html = panel._get_html_template()
    
    # Should use local script references, not external CDNs
    assert "cdn.jsdelivr.net" not in html
    assert 'src="marked.min.js"' in html
    assert 'src="purify.min.js"' in html
    assert 'src="tex-mml-chtml.js"' in html
    assert "Content-Security-Policy" in html
    assert "DOMPurify.sanitize" in html
