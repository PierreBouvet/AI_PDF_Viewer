"""
Utility module for locating and loading offline assets (JavaScript libraries, icons, etc.)
Supports both development mode and PyInstaller frozen bundle execution.
"""
import os
import sys
from PySide6.QtCore import QUrl
from backend.logger import logger

def get_assets_dir() -> str:
    """Returns absolute path to the assets directory."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        
    assets_path = os.path.join(base, "assets")
    if os.path.exists(assets_path):
        return assets_path
    return os.path.abspath("assets")

def get_asset_path(filename: str) -> str:
    """Returns absolute path to a specific file inside assets directory."""
    return os.path.join(get_assets_dir(), filename)

def read_asset_text(filename: str) -> str:
    """Reads and returns text content of an asset file."""
    path = get_asset_path(filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading asset {filename}: {e}")
    return ""

def get_assets_base_url() -> QUrl:
    """Returns QUrl pointing to the assets directory for QWebEngine setHtml base."""
    return QUrl.fromLocalFile(get_assets_dir() + os.path.sep)
