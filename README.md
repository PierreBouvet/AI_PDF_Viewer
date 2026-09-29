# AI PDF Viewer

![Version](https://img.shields.io/badge/version-1.0_beta-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

AI PDF Viewer is a local, desktop-based graphical application built with Python and PySide6 (Qt) that allows you to read, annotate, and chat with your PDF documents using either Google's powerful Gemini AI models or local models hosted and run via Ollama. Its goal is to have a desktop-ready tool that can be used specifically for literature review, working as a standard PDF viewer but with the added ability to (1)chat with your document and (2) use custom pipelines to "enter" into your document: if you like to have a short (100 word) summary of the work, then a 200 word summary of the conclusions, a bullet point presentation of the methods and a list of the hypothesis being checked, you can write a complex prompt detailing what you expect, save it and reuse it for every new paper you want to read with a single click.

This initial application is the first autonomous part of a larger AI-for-science project that I am developing, where a final product will be able to fully automate the literature review process for scientists and researchers and personalize the way we read and interact with scientific literature.

This project is in beta stage, it has been (heavily) tested on MacOS but is still subject to bugs and unexpected behavior. You can report issues on the issue tracker. 

Note that all the bugs that you are likely to encounter will by design NOT compromise the security or privacy of your document or allow unwanted backdoors to your computer. This particularly includes your Google API key which is secured in the keyring of your computer (MacOS, Windows or Linux) and will be deleted from memory when the app is closed. If you're using the app in a professional/secure environment, I recommend running the app with a local model via Ollama to ensure the privacy of your documents. 

For the choice of models, no benchmarks have been developed so I can only give a qualitative opinion based on my personal experience. For Gemini models accesible via API, you will not notice a significant difference between the models for summarizing and Q&A on the articles. You might start to see marginal gains if you start asking expert quesitons when using the heavier models, but I personnally default to a standard Flash lite model in my everyday use. 

For local models, the situation is a bit different, it mainly depends on your hardware. On a high end machine with a dedicated GPU, you'll be able to run large models with no performance penalty, on "average" laptops (e.g. a MacBook Pro with 16Gb of RAM), I have found Qwen 2.5 7B or Llama 3.1 8B to be good starting points. Expect however a significant speed difference between the cloud models (responds usually in less than a second - except when there's heavy traffic on google servers) and the local models (responds usually in several seconds, tens of seconds or minutes depending on prompt complexity). 

## Features

- **Modern PDF Reader**: Render and navigate PDFs smoothly with thumbnail previews, built on top of `pymupdf`.
- **Interactive PDF Annotations**: Uses a floating toolbar to add highlights (text and freehand), text boxes, and sticky notes directly onto the document. Annotations are saved in standard PDF formats and persist across different viewers.
- **AI Chat & Q&A**: Chat directly with your PDF document. The app indexes the document contents securely via either the Gemini API or a local model (via Ollama), enabling deep contextual analysis and Q&A.
- **Granular Page Selection**: Choose exactly which pages to include or exclude from the AI's context to save tokens and focus the AI on relevant sections.
- **Custom Prompts Library**: Save, edit, and quickly access your frequently used prompts (e.g., "Summarize this page", "Extract methodology") via a persistent prompt library.
- **Markdown-Rich Chat Interface**: Beautifully formatted chat bubbles that support rich markdown, code blocks, and dynamic UI updates (built with QWebEngineView).
- **Edit AI Responses**: A built-in editor allows you to tweak and correct the AI's markdown responses directly within the chat interface.
- **Store AI Responses**: You can export responses of the chat directly as a PDF and append this PDF to your article.
- **Smart AI response Time Estimator**: When running local models via Ollama, the app benchmarks the token throughput of your past queries. It automatically estimates and displays how long complex prompts will take to finish based on the previous runs. 
- **Secure Configuration**: Save your Google API key securely in your system's keychain. Switch seamlessly between different Gemini models via the built-in AI Configurator.
- **Customizable UI**: Switch between light and dark modes, and adjust the AI chat font family and sizing to your preference.
- **Advanced Structured Extraction**: For documents with complex layouts or tables, you can optionally install [opendataloader-pdf](https://github.com/pbouvet/opendataloader-pdf) (via `pip install opendataloader-pdf`). If detected, the app will automatically use it to extract high-quality Markdown/JSON structures, significantly improving the AI's understanding of the document's layout.

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
1. **Configure AI Provider**: Click on the **"AI configuration"** button (`⚙️`) in the toolbar.
   - **Cloud**: Select **Cloud (Google Gemini)**, enter your Gemini API key, and choose your preferred model.
   - **Local (Offline)**: Select **Local Model (Mistral / GGUF)** to connect to a local runner like **Ollama** or pick a local model file.
2. **Open a PDF**: Drag and drop a PDF into the main window or click **"Open PDF"**.
3. **Index the Document**: Once loaded, click the blue **"Index PDF to enable AI Q&A"** button in the chat panel. This prepares the document for the AI.
4. **Chat**: Type a question in the chat box, select a pre-defined prompt from the dropdown, or right-click / select text to explain and discuss passages!

## Building the App

If you want to package AI PDF Viewer into a standalone `.app` bundle for macOS or a standalone executable, we use `pyinstaller`. Please refer to the detailed instructions in [BUILD.md](BUILD.md).

Note: Because your API key is stored in the keyring of your computer, when running the application as an executable, you will be prompted to enter your user password to allow the application to access your API key. This is normal behavior but it currently has no fallback if you don't want to enter your password. 

---

## Running Models Locally with Ollama

Running a local model ensures **100% privacy**, eliminates **503 service unavailable / rate-limit errors**, and allows the app to function completely **offline**.

### 1. Install Ollama

- **macOS**:
  ```bash
  # Using Homebrew
  brew install ollama
  # Or download directly from https://ollama.com/download
  ```
- **Linux**:
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ```
- **Windows**:
  Download and install the official installer from [ollama.com/download](https://ollama.com/download).

Start the Ollama background service if it is not already running:
```bash
ollama serve
```

---

### 2. Download & Run Recommended Models

#### **Qwen 2.5 7B (Recommended)**
Qwen 2.5 is an exceptional choice for scientific research papers, technical documents, and complex reasoning. It features a native **128k context window** and runs smoothly on Apple Silicon (M1/M2/M3/M4) and modern GPUs with reasonable RAM (I personally have 16Gb of RAM, and it runs pretty well).

```bash
# Pull and start Qwen 2.5 (approx. 7.1 GB)
ollama pull qwen2.5:7b
```

#### Other Excellent Local Models:
| Model | Command | Context Window | Best For |
|---|---|---|---|
| **Llama 3.1 8B** | `ollama pull llama3.1:8b` | 128k tokens | General document Q&A and fast summarization |
| **Phi-3.5 Mini 3.8B** | `ollama pull phi3.5` | 128k tokens | Lightweight machines and laptops |
| **Mistral NeMo 12B** | `ollama pull mistral-nemo:12b` | 128k tokens | Research papers, reasoning, math |

---

### 3. Setting a Large Context Window in Ollama (For Long PDFs)

By default, Ollama allocates a 2,048 or 4,096 token context window unless configured otherwise. To enable large document analysis across 30+ pages, create a custom model preset with a larger context:

1. Create a file named `Modelfile`:
   ```dockerfile
   FROM mistral-nemo:12b
   PARAMETER num_ctx 32768
   PARAMETER temperature 0.3
   ```
2. Build the model in Ollama:
   ```bash
   ollama create mistral-nemo-32k -f Modelfile
   ```

---

### 4. Configure AI PDF Viewer to Use Ollama

1. Open AI PDF Viewer and click **Settings** (`Cmd+,` or toolbar button) > **AI** tab.
2. Select **Local (Ollama / Local LLM)**.
3. The app automatically detects installed models from Ollama; choose your model (e.g., `mistral-nemo:latest`) from the dropdown.
4. Click **"Save Settings"** (`OK`).
5. Open your PDF and click **"Index PDF"** to analyze documents with your local Ollama model!

---

## Project Structure

- `main.py`: The entry point for the application.
- `backend/`: Core logic including `AIAssistant` (Gemini & Local LLM integration), `PDFDocument` (PyMuPDF wrapper), `ConfigManager`, and `PromptsManager`.
- `ui/`: PySide6 interface components (`MainWindow`, `PDFView`, `AIChatPanel`, `ThumbnailPanel`, dialogs, etc.).
- `assets/`: Offline assets (`qwebchannel.js`, `marked.min.js`, `purify.min.js`, `tex-mml-chtml.js`).
- `icons/`: High-DPI and vector application icons.
- `custom_prompts.csv`: User-defined prompt library.

## Technologies Used

- **GUI Framework**: PySide6 (Qt for Python)
- **PDF Rendering**: PyMuPDF (`pymupdf`)
- **AI Integration**: Google GenAI SDK (`google-genai`) & Local OpenAI-compatible API (Ollama, LM Studio)
- **Web Rendering**: QtWebEngine & QWebChannel
- **Security**: keyring (for secure credential storage)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
