import csv
import os

class PromptsManager:
    def __init__(self, file_path="custom_prompts.csv"):
        self.file_path = file_path

    def load_prompts(self) -> dict:
        """Returns a dict of {expression: prompt_text}"""
        prompts = {}
        if not os.path.exists(self.file_path):
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
            print(f"Error loading prompts: {e}")
            
        return prompts

    def save_prompts(self, prompts: dict):
        try:
            with open(self.file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                for expr, text in prompts.items():
                    writer.writerow([expr, text])
        except Exception as e:
            print(f"Error saving prompts: {e}")
