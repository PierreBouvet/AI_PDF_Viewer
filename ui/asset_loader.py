"""
Utility module for locating and loading offline assets (JavaScript libraries, icons, etc.)
Supports development mode, PyInstaller frozen bundles (Windows, macOS, Linux), and cross-platform execution.
"""
import os
import sys
from PySide6.QtCore import QUrl
from backend.logger import logger

def get_bundle_dir() -> str:
    """
    Returns the absolute path to the application bundle root directory across OSes and packaging modes.
    - When frozen via PyInstaller: sys._MEIPASS (or dirname(sys.executable))
    - When running from source: project root directory (parent of ui/)
    """
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_assets_dir() -> str:
    """Returns absolute path to the assets directory."""
    return os.path.join(get_bundle_dir(), "assets")

def get_icons_dir() -> str:
    """Returns absolute path to the icons directory."""
    return os.path.join(get_bundle_dir(), "icons")

def get_icon_path(filename: str) -> str:
    """Returns absolute path to a specific file inside icons directory."""
    return os.path.join(get_icons_dir(), filename)

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
