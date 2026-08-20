# AI PDF Viewer

AI PDF Viewer is a local, desktop-based graphical application built with Python and PySide6 (Qt) that allows you to read, annotate, and chat with your PDF documents using Google's powerful Gemini AI models. 

By integrating a traditional PDF reading experience with advanced Large Language Models, you can seamlessly index documents, ask complex questions, summarize sections, and interact with your texts intelligently.

## Features

- **Modern PDF Reader**: Render and navigate PDFs smoothly with thumbnail previews, built on top of `pymupdf`.
- **AI Chat & Q&A**: Chat directly with your PDF document. The app indexes the document contents securely via the Gemini API, enabling deep contextual analysis and Q&A.
- **Granular Page Selection**: Choose exactly which pages to include or exclude from the AI's context to save tokens and focus the AI on relevant sections.
- **Custom Prompts Library**: Save, edit, and quickly access your frequently used prompts (e.g., "Summarize this page", "Extract methodology") via a persistent CSV-backed prompts library.
- **Markdown-Rich Chat Interface**: Beautifully formatted chat bubbles that support rich markdown, code blocks, and dynamic UI updates (built with QWebEngineView).
- **Edit AI Responses**: A built-in editor allows you to tweak and correct the AI's markdown responses directly within the chat interface.
- **Secure Configuration**: Save your Google API key securely in your system's keychain. Switch seamlessly between different Gemini models (e.g., Gemini 1.5 Pro, Gemini 3.5 Flash) via the built-in AI Configurator.
- **Customizable UI**: Switch between light and dark modes, and adjust the AI chat font family and sizing to your preference.

## Prerequisites

- Python 3.9+
- A Google Gemini API Key. You can get one from [Google AI Studio](https://aistudio.google.com/).

## Installation

1. **Clone or Download the Repository:**
   Ensure you have downloaded the project to your local machine.

2. **Set up a Virtual Environment (Recommended):**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the main application script:

```bash
python main.py
```

### Getting Started:
1. **Configure API Key**: Click on the **"AI configuration"** button in the toolbar. Enter your Gemini API key and select your preferred model. Your API key will be saved securely to your system keychain.
2. **Open a PDF**: Drag and drop a PDF into the main window or click **"Open PDF"**.
3. **Index the Document**: Once loaded, click the blue **"Index PDF to enable AI Q&A"** button in the chat panel. This prepares the document for the AI.
4. **Chat**: Type a question in the chat box or use the dropdown to select a pre-defined prompt!

## Project Structure

- `main.py`: The entry point for the application.
- `backend/`: Core logic including the `AIAssistant` (Gemini API interactions), `PDFDocument` (PyMuPDF wrapper), `ConfigManager`, and `PromptsManager`.
- `ui/`: PySide6 interface components (`MainWindow`, `PDFView`, `AIChatPanel`, `ThumbnailPanel`, dialogs, etc.).
- `icons/`: Project assets and icons.
- `custom_prompts.csv`: User-defined prompt library.

## Technologies Used

- **GUI Framework**: PySide6 (Qt for Python)
- **PDF Rendering**: PyMuPDF (`pymupdf`)
- **AI Integration**: Google GenAI SDK (`google-genai`)
- **Web Rendering**: QtWebEngine
- **Theming**: qt-material
- **Security**: keyring (for secure credential storage)
