import os
from dotenv import load_dotenv
from ollama import Client

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

def test_ollama():
    client = Client(
        host="https://ollama.com",
        headers={'Authorization': 'Bearer ' + GEMINI_API_KEY}
    )
    
    user_input = "Hello, are you working?"
    
    messages = [
        {
            'role': 'user',
            'content': user_input,
        },
    ]
    
    print("Sending request to Ollama cloud...")
    try:
        response = client.chat(
            model='gemini-3-flash-preview:cloud',
            messages=messages
        )
        
        generated_text = response['message']['content']
        print("\n--- Generated Response ---")
        print(generated_text)
        print("--------------------------")
        print("Ollama API is working correctly!")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_ollama()
