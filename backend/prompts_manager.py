import csv
import os
import shutil
import sys
from PySide6.QtCore import QStandardPaths
from backend.logger import logger

def get_bundle_dir() -> str:
    """Returns absolute path to the application bundle/root directory across OSes and packaging modes."""
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

class PromptsManager:
    def __init__(self, file_path: str = None):
        if file_path:
            self.file_path = file_path
        else:
            app_data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
            os.makedirs(app_data_dir, exist_ok=True)
            self.file_path = os.path.join(app_data_dir, "custom_prompts.csv")

    def load_prompts(self) -> dict:
        """Returns a dict of {expression: prompt_text}"""
        prompts = {}
        if not os.path.exists(self.file_path):
            # Check for bundled template first
            bundled_template = os.path.join(get_bundle_dir(), "custom_prompts.csv")
            seeded = False
            if os.path.exists(bundled_template) and os.path.abspath(bundled_template) != os.path.abspath(self.file_path):
                try:
                    shutil.copy2(bundled_template, self.file_path)
                    seeded = True
                except Exception as e:
                    logger.warning(f"Could not copy bundled prompts template: {e}")
            if not seeded:
                # Create default if missing
                self.save_prompts({
                    "Bullet summary": "Summarize this paper in bullet points. You should summarize the paper in a list of bullet points of 2 levels: the first level should summarize the basic ideas, the second levels should focus on the technical aspects regarding either presented results, methods or sources. Use at least 3 main bullet points, ideally 5 and less than 10."
                })
            
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        prompts[row[0].strip()] = row[1].strip()
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            
        return prompts

    def save_prompts(self, prompts: dict):
        try:
            dir_name = os.path.dirname(self.file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                for expr, text in prompts.items():
                    writer.writerow([expr, text])
        except Exception as e:
            logger.error(f"Error saving prompts: {e}")
