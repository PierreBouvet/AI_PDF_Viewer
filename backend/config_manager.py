from PySide6.QtCore import QSettings

class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.settings = QSettings("AIPDFViewer", "Settings")

    @property
    def model_name(self) -> str:
        return str(self.settings.value("model_name", "gemini-3.5-flash-lite"))

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
        return str(self.settings.value("app_style", "Native macOS"))

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
