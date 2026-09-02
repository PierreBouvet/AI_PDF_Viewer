import os
import json
from datetime import datetime, timedelta
from typing import Optional
from google import genai
from google.genai import types
from PySide6.QtCore import QSettings
import keyring
from backend.logger import logger

FREE_TIER_QUOTAS = {
    "gemini-1.5-flash": {"RPM": 15, "RPD": 1000000},
    "gemini-1.5-flash-8b": {"RPM": 15, "RPD": 1000000},
    "gemini-1.5-pro": {"RPM": 2, "RPD": 50},
    "gemini-2.0-flash-exp": {"RPM": 10, "RPD": 1500},
    "gemini-2.5-flash": {"RPM": 15, "RPD": 1000000},
    "gemini-3.5-flash": {"RPM": 15, "RPD": 1000000},
}

class AIAssistant:
    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.model_name = model_name
        self.uploaded_file = None
        self.chat_session = None
        self.ranked_models = []
        
        self._initialize_models()

    def _get_api_key(self) -> str:
        try:
            return keyring.get_password("AIPDFViewer", "api_key") or ""
        except Exception:
            return ""

    def _get_client(self):
        api_key = self._get_api_key()
        if not api_key:
            return None
        try:
            return genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Error initializing generative AI client: {e}")
            return None

    def set_model_name(self, model_name: str):
        self.model_name = model_name
        self._initialize_models()

    def _initialize_models(self):
        client = self._get_client()
        if client and self.uploaded_file:
            self._build_chat_session(client)

    def rank_available_models(self) -> list:
        client = self._get_client()
        if not client:
            return []
            
        settings = QSettings("AIPDFViewer", "ModelsCache")
        cached_date_str = settings.value("last_updated")
        cached_models_str = settings.value("ranked_models")
        
        # Check cache validity (14 days)
        if cached_date_str and cached_models_str:
            try:
                last_updated = datetime.fromisoformat(cached_date_str)
                if datetime.now() - last_updated < timedelta(days=14):
                    self.ranked_models = json.loads(cached_models_str)
                    if self.ranked_models:
                        return self.ranked_models
            except Exception as e:
                logger.error(f"Cache read error: {e}")
                
        # If no cache or expired, fetch from API
        try:
            available_models = []
            for m in client.models.list():
                if "gemini" in m.name and "vision" not in m.name:
                    available_models.append(m.name)
            
            clean_available = [m.replace("models/", "") for m in available_models]
            
            # Use a pro model for classification
            pro_model = next((m for m in clean_available if "pro" in m), "gemini-2.5-flash")
            
            prompt = (
                f"Here are available Gemini models: {clean_available}. "
                "Rank them from best suited to least well suited for a PDF reading and analysis application. "
                "Consider context length and reasoning capability. "
                "Return exactly the top 10 as a JSON list of strings (e.g. ['gemini-2.5-flash', ...]). Do not return markdown, just the JSON array."
            )
            
            chat = client.chats.create(model=pro_model)
            response = chat.send_message(prompt)
            
            # Extract JSON list safely
            text = response.text.replace("```json", "").replace("```", "").strip()
            top_10 = json.loads(text)
            
            # Filter and validate only models that actually exist
            valid_top = [m.replace("models/", "") for m in top_10 if m.replace("models/", "") in clean_available]
            if not valid_top:
                valid_top = clean_available[:10]
            
            # Attach quota info and sort by fewest restrictions (highest RPM/RPD)
            models_with_quota = []
            for base_name in valid_top:
                quota = FREE_TIER_QUOTAS.get(base_name, {"RPM": 0, "RPD": 0})
                models_with_quota.append({
                    "name": base_name,
                    "RPM": quota["RPM"],
                    "RPD": quota["RPD"]
                })
                
            # Sort by RPD descending, then RPM descending
            models_with_quota.sort(key=lambda x: (x["RPD"], x["RPM"]), reverse=True)
            
            self.ranked_models = models_with_quota
                
            # Cache it
            settings.setValue("last_updated", datetime.now().isoformat())
            settings.setValue("ranked_models", json.dumps(self.ranked_models))
            return self.ranked_models
            
        except Exception as e:
            logger.error(f"Failed to rank models: {e}")
            return self.ranked_models

    def clear_index(self):
        """Clear the current uploaded file to avoid querying an old document."""
        client = self._get_client()
        if self.uploaded_file and client:
            try:
                client.files.delete(name=self.uploaded_file.name)
            except Exception as e:
                logger.error(f"Failed to delete remote file: {e}")
        self.uploaded_file = None
        self.chat_session = None
        
    def index_pdf(self, file_path: str, excluded_pages: set = None, included_pages: set = None):
        """Upload the PDF directly to Gemini via the File API."""
        client = self._get_client()
        if not client:
            raise ValueError("API key not set.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Clear any existing file first
        self.clear_index()
        
        excluded_pages = excluded_pages or set()
        included_pages = included_pages or set()
        
        import pymupdf as fitz
        import tempfile
        
        doc = fitz.open(file_path)
        clean_doc = fitz.open()
        has_ai_pages = False
        
        for page in doc:
            page_num = page.number
            
            if page_num in excluded_pages:
                has_ai_pages = True
                continue
                
            if page_num in included_pages:
                clean_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                continue
                
            text = page.get_text()
            if "[[AI_GENERATED_PAGE]]" in text or "Generated by gemini-" in text:
                has_ai_pages = True
            else:
                clean_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                
        if has_ai_pages:
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            clean_doc.save(temp_path)
            upload_path = temp_path
        else:
            upload_path = file_path
            
        clean_doc.close()
        doc.close()

        logger.info(f"Uploading {upload_path} to Gemini...")
        self.uploaded_file = client.files.upload(file=upload_path)
        logger.info(f"Uploaded as: {self.uploaded_file.name}")
        
        if has_ai_pages and os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except Exception as e:
                logger.error(f"Failed to remove temp file: {e}")
        
        self._build_chat_session(client)

    def _build_chat_session(self, client):
        if not self.uploaded_file or not client:
            return
            
        # Start a chat session
        self.chat_session = client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction="You are a helpful assistant analyzing a PDF document.",
                temperature=0.3
            )
        )
        
        # Send the file as the first message to establish context
        try:
            self.chat_session.send_message([
                self.uploaded_file, 
                "Here is the document. Please use it to answer my upcoming questions. Keep answers concise, around 3 sentences maximum unless requested otherwise."
            ])
        except Exception as e:
            logger.error(f"Failed to initialize chat context: {e}")

    def ask(self, question: str) -> str:
        """Ask a question using the uploaded document context."""
        client = self._get_client()
        if not client:
            raise ValueError("Please configure your Google API Key in the settings.")
            
        if not self.chat_session:
            raise ValueError("No document is currently indexed. Please load a PDF and click Index first.")

        response = self.chat_session.send_message(question)
        return response.text

    def ask_direct(self, question: str, model_override: str = "") -> str:
        """Ask a question directly to the LLM without mutating persistent assistant model state."""
        client = self._get_client()
        if not client:
            raise ValueError("Please configure your Google API Key in the settings.")

        target_model = model_override or self.model_name
        chat = client.chats.create(model=target_model)
        if self.uploaded_file:
            response = chat.send_message([self.uploaded_file, question])
        else:
            response = chat.send_message(question)
            
        return response.text

