import os
import json
from datetime import datetime, timedelta
from typing import Optional
from google import genai
from google.genai import types
from PySide6.QtCore import QSettings

FREE_TIER_QUOTAS = {
    "gemini-1.5-flash": {"RPM": 15, "RPD": 1000000},
    "gemini-1.5-flash-8b": {"RPM": 15, "RPD": 1000000},
    "gemini-1.5-pro": {"RPM": 2, "RPD": 50},
    "gemini-2.0-flash-exp": {"RPM": 10, "RPD": 1500},
    "gemini-2.5-flash": {"RPM": 15, "RPD": 1000000},
    "gemini-3.5-flash": {"RPM": 15, "RPD": 1000000},
}

class AIAssistant:
    def __init__(self, api_key: str = "", model_name: str = "gemini-3.5-flash-lite"):
        self.api_key = api_key
        self.model_name = model_name
        self.uploaded_file = None
        self.chat_session = None
        self.client = None
        self.ranked_models = []
        
        if self.api_key:
            self._initialize_models()

    def set_api_key(self, api_key: str):
        self.api_key = api_key
        if self.api_key:
            self._initialize_models()

    def set_model_name(self, model_name: str):
        self.model_name = model_name
        if self.api_key:
            self._initialize_models()

    def _initialize_models(self):
        try:
            self.client = genai.Client(api_key=self.api_key)
            # Recreate chat session if we already have an uploaded file
            if self.uploaded_file:
                self._build_chat_session()
        except Exception as e:
            print(f"Error initializing generative AI: {e}")

    def rank_available_models(self):
        if not self.api_key or not self.client:
            return
            
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
                        # Set default to the one with the fewest quota restrictions (highest quota)
                        self.model_name = self.ranked_models[0]["name"]
                        return
            except Exception as e:
                print(f"Cache read error: {e}")
                
        # If no cache or expired, fetch from API
        try:
            available_models = []
            for m in self.client.models.list():
                if "gemini" in m.name and "vision" not in m.name:
                    available_models.append(m.name)
            
            # Use a pro model for classification
            pro_model = next((m for m in available_models if "pro" in m), "gemini-3.7-flash")
            pro_model = pro_model.replace("models/", "")
            
            prompt = (
                f"Here are available Gemini models: {available_models}. "
                "Rank them from best suited to least well suited for a PDF reading and analysis application. "
                "Consider context length and reasoning capability. "
                "Return exactly the top 10 as a JSON list of strings (e.g. ['gemini-3.5-flash', ...]). Do not return markdown, just the JSON array."
            )
            
            chat = self.client.chats.create(model=pro_model)
            response = chat.send_message(prompt)
            
            # Extract JSON list
            text = response.text.replace("```json", "").replace("```", "").strip()
            top_10 = json.loads(text)
            
            # Attach quota info and sort by fewest restrictions (highest RPM/RPD)
            models_with_quota = []
            for m in top_10:
                base_name = m.replace("models/", "")
                quota = FREE_TIER_QUOTAS.get(base_name, {"RPM": 0, "RPD": 0})
                models_with_quota.append({
                    "name": base_name,
                    "RPM": quota["RPM"],
                    "RPD": quota["RPD"]
                })
                
            # Sort by RPD descending, then RPM descending
            models_with_quota.sort(key=lambda x: (x["RPD"], x["RPM"]), reverse=True)
            
            self.ranked_models = models_with_quota
            if self.ranked_models:
                self.model_name = self.ranked_models[0]["name"]
                
            # Cache it
            settings.setValue("last_updated", datetime.now().isoformat())
            settings.setValue("ranked_models", json.dumps(self.ranked_models))
            
        except Exception as e:
            print(f"Failed to rank models: {e}")

    def clear_index(self):
        """Clear the current uploaded file to avoid querying an old document."""
        if self.uploaded_file and self.client:
            try:
                self.client.files.delete(name=self.uploaded_file.name)
            except:
                pass
        self.uploaded_file = None
        self.chat_session = None
        
    def index_pdf(self, file_path: str, excluded_pages: set = None, included_pages: set = None):
        """Upload the PDF directly to Gemini via the File API."""
        if not self.api_key or not self.client:
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

        print(f"Uploading {upload_path} to Gemini...")
        self.uploaded_file = self.client.files.upload(file=upload_path)
        print(f"Uploaded as: {self.uploaded_file.name}")
        
        if has_ai_pages and os.path.exists(upload_path):
            try:
                os.remove(upload_path)
            except Exception as e:
                print(f"Failed to remove temp file: {e}")
        
        self._build_chat_session()

    def _build_chat_session(self):
        if not self.uploaded_file or not self.client:
            return
            
        # Start a chat session
        self.chat_session = self.client.chats.create(
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
            print(f"Failed to initialize chat context: {e}")

    def ask(self, question: str) -> str:
        """Ask a question using the uploaded document context."""
        if not self.api_key or not self.client:
            raise ValueError("Please configure your Google API Key in the settings.")
            
        if not self.chat_session:
            raise ValueError("No document is currently indexed. Please load a PDF and click Index first.")

        response = self.chat_session.send_message(question)
        return response.text

    def ask_direct(self, question: str) -> str:
        """Ask a question directly to the LLM. Includes the file if available, otherwise just text."""
        if not self.api_key or not self.client:
            raise ValueError("Please configure your Google API Key in the settings.")

        chat = self.client.chats.create(model=self.model_name)
        if self.uploaded_file:
            response = chat.send_message([self.uploaded_file, question])
        else:
            response = chat.send_message(question)
            
        return response.text

