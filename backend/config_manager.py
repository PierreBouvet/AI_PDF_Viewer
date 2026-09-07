from PySide6.QtCore import QSettings

# Default fallback model when no specific model has been selected or saved.
DEFAULT_FALLBACK_MODEL = "gemini-flash-lite-latest"

class ConfigManager:
    _instance = None

    @classmethod
    def reset(cls):
        """Reset the singleton instance (primarily for testing and context teardown)."""
        cls._instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.settings = QSettings("AIPDFViewer", "Settings")

    @property
    def model_name(self) -> str:
        return str(self.settings.value("model_name", ""))

    @model_name.setter
    def model_name(self, value: str):
        self.settings.setValue("model_name", value)
        self.settings.sync()

    @property
    def ai_font_family(self) -> str:
        return self.settings.value("ai_font_family", "Optima")

    @ai_font_family.setter
    def ai_font_family(self, value: str):
        self.settings.setValue("ai_font_family", value)

    @property
    def ai_font_size(self) -> int:
        return int(self.settings.value("ai_font_size", 11))

    @ai_font_size.setter
    def ai_font_size(self, value: int):
        self.settings.setValue("ai_font_size", value)

    @property
    def app_style(self) -> str:
        return str(self.settings.value("app_style", "Native"))

    @app_style.setter
    def app_style(self, value: str):
        self.settings.setValue("app_style", value)
        self.settings.sync()

    @property
    def color_mode(self) -> str:
        return str(self.settings.value("color_mode", "System (Auto)"))

    @color_mode.setter
    def color_mode(self, value: str):
        self.settings.setValue("color_mode", value)
        self.settings.sync()

    @property
    def ai_provider(self) -> str:
        """Active AI provider: 'cloud' (Google Gemini) or 'local' (Local Model)."""
        return str(self.settings.value("ai_provider", "cloud"))

    @ai_provider.setter
    def ai_provider(self, value: str):
        self.settings.setValue("ai_provider", value)
        self.settings.sync()



    @property
    def local_endpoint_url(self) -> str:
        """OpenAI-compatible local inference endpoint (e.g., http://localhost:11434/v1)."""
        return str(self.settings.value("local_endpoint_url", "http://localhost:11434/v1"))

    @local_endpoint_url.setter
    def local_endpoint_url(self, value: str):
        self.settings.setValue("local_endpoint_url", value)
        self.settings.sync()

    @property
    def local_model_name(self) -> str:
        """Local model identifier name (e.g. mistral-nemo:latest)."""
        val = str(self.settings.value("local_model_name", "mistral-nemo:latest"))
        # Sanitize legacy file names that may have been saved previously from file picker
        if any(ext in val.lower() for ext in [".gguf", ".bin", ".safetensors", ".q4_", ".q5_", ".q8_"]):
            return "mistral-nemo:latest"
        return val or "mistral-nemo:latest"

    @local_model_name.setter
    def local_model_name(self, value: str):
        self.settings.setValue("local_model_name", value)
        self.settings.sync()

    @property
    def local_timeout_sec(self) -> int:
        """Timeout in seconds for local AI model inference requests (default: 300s / 5 min)."""
        try:
            val = int(self.settings.value("local_timeout_sec", 300))
            return max(10, min(1800, val))
        except (ValueError, TypeError):
            return 300

    @local_timeout_sec.setter
    def local_timeout_sec(self, value: int):
        self.settings.setValue("local_timeout_sec", int(value))
        self.settings.sync()


