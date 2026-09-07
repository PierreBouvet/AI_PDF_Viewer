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
1. **Configure AI Provider**: Click on the **"AI configuration"** button (`⚙️`) in the toolbar.
   - **Cloud**: Select **Cloud (Google Gemini)**, enter your Gemini API key, and choose your preferred model.
   - **Local (Offline)**: Select **Local Model (Mistral / GGUF)** to connect to a local runner like **Ollama** or pick a local model file.
2. **Open a PDF**: Drag and drop a PDF into the main window or click **"Open PDF"**.
3. **Index the Document**: Once loaded, click the blue **"Index PDF to enable AI Q&A"** button in the chat panel. This prepares the document for the AI.
4. **Chat**: Type a question in the chat box, select a pre-defined prompt from the dropdown, or right-click / select text to explain and discuss passages!

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

#### **Mistral NeMo 12B (Highly Recommended)**
Created jointly by Mistral AI and NVIDIA, **Mistral NeMo 12B** is an exceptional choice for scientific research papers, technical documents, and complex reasoning. It features a native **128k context window** and runs smoothly on Apple Silicon (M1/M2/M3/M4) and modern GPUs.

```bash
# Pull and start Mistral NeMo (approx. 7.1 GB)
ollama pull mistral-nemo:12b
```

#### Other Excellent Local Models:
| Model | Command | Context Window | Best For |
|---|---|---|---|
| **Mistral NeMo 12B** | `ollama pull mistral-nemo:12b` | 128k tokens | **Research papers, reasoning, math** (Recommended) |
| **Llama 3.1 8B** | `ollama pull llama3.1:8b` | 128k tokens | General document Q&A and fast summarization |
| **Qwen 2.5 7B / 14B** | `ollama pull qwen2.5:7b` | 128k tokens | Multilingual texts, tables, and structured data |
| **Phi-3.5 Mini 3.8B** | `ollama pull phi3.5` | 128k tokens | Lightweight machines and laptops |

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

### 4. Running Custom GGUF Model Files

If you downloaded a `.gguf` model file directly (e.g. from Hugging Face), you can import it into Ollama:

1. Create a `Modelfile`:
   ```dockerfile
   FROM /path/to/your/model.gguf
   PARAMETER num_ctx 32768
   PARAMETER temperature 0.3
   ```
2. Build the model in Ollama:
   ```bash
   ollama create my-custom-model -f Modelfile
   ```

---

### 5. Configure AI PDF Viewer to Use Ollama

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

