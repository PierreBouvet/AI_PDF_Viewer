# Building the AI PDF Viewer Executable

This guide explains how to build standalone executables and macOS application bundles (`.app`) for **AI PDF Viewer**.

---

## 1. Prerequisites

Make sure the project virtual environment is activated and all dependencies (including `pyinstaller`) are installed:

```bash
# Activate virtual environment
source .venv/bin/activate

# Install requirements
pip install -r requirements.txt
pip install pyinstaller
```

---

## 2. Building on macOS (Creates `.app` Bundle & CLI Executable)

We use the pre-configured [`AI PDF Viewer.spec`](AI%20PDF%20Viewer.spec) file, which bundles the application icon (`icons/icon.icns`), UI assets (`icons/*.svg`), and presets (`custom_prompts.csv`).

Run the following command in the root repository directory:

```bash
pyinstaller "AI PDF Viewer.spec" --noconfirm
```

### Build Outputs
After the build completes, your packaged artifacts will be located in the `dist/` directory:
- **macOS App Bundle**: `dist/AI PDF Viewer.app` (Can be copied directly into `/Applications`)
- **Folder Executable**: `dist/AI PDF Viewer/AI PDF Viewer`

---

## 3. Launching / Testing the Built Application

### Direct Command Line Launch:
```bash
# Launch macOS app bundle
open "dist/AI PDF Viewer.app"

# Or run the standalone executable directly
./dist/AI\ PDF\ Viewer/AI\ PDF\ Viewer
```

### Opening with a PDF:
```bash
open -a "dist/AI PDF Viewer.app" path/to/document.pdf
```

---

## 4. Building from Scratch (Alternative / Custom Spec Generation)

If you ever need to regenerate the spec file from scratch:

```bash
pyinstaller --name "AI PDF Viewer" \
            --windowed \
            --icon "icons/icon.icns" \
            --add-data "icons:icons" \
            --add-data "custom_prompts.csv:." \
            --hidden-import "PySide6.QtSvg" \
            --hidden-import "PySide6.QtSvgWidgets" \
            --noconfirm \
            main.py
```

---

## 5. Clean Build (Troubleshooting)

To perform a completely fresh build and clear previous caches:

```bash
rm -rf build dist
pyinstaller "AI PDF Viewer.spec" --noconfirm --clean
```
