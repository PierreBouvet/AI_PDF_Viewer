import os
import requests
from dotenv import load_dotenv

class APIClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://meduniwien-api.academic-ai.at"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

    def create_chat_completion(self, model: str, messages: list, **kwargs):
        url = f"{self.base_url}/api/v1/llm/chat" 
        headers ={
             "X-Client-ID": self.api_key, 
             "X-Client-Secret": self.api_secret, 
             "Content-Type": "application/json", 
            }
        payload = { "model": model, "messages": messages, **kwargs, }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()


load_dotenv()

api = APIClient(api_key = os.environ["CLIENT_ID"], api_secret = os.environ["CLIENT_SECRET"])

response = api.create_chat_completion(
    model = "gpt-4o",
    messages = [
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    temperature = 0.7,
    maxTokens = 1000,
)

print(f"Response: {response['data']['content']}")
print(f"Tokens used:{response['data']['usage']['totalTokens']}")