import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

def test_gemini():
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }
    
    user_input = "Hello, are you working?"
    
    data = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": user_input}
                ],
            }
        ]
    }
    
    print(f"Sending request to {url}...")
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            # print(json.dumps(result, indent=2)) # Uncomment to see full response
            
            try:
                generated_text = result["candidates"][0]["content"]["parts"][0]["text"]
                print("\n--- Generated Response ---")
                print(generated_text)
                print("--------------------------")
                print("Gemini API is working correctly!")
            except (KeyError, IndexError) as e:
                print("Error parsing response structure:", e)
                print("Full response:", result)
        else:
            print("Error response:", response.text)
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_gemini()
