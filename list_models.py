import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def list_models():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        models = response.json().get('models', [])
        print("Available models:")
        for model in models:
            if 'generateContent' in model.get('supportedGenerationMethods', []):
                print(f"- {model['name']}")
    else:
        print(f"Error listing models: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    list_models()
