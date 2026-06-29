import os
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI

print("GEMINI_API_KEY exists:", bool(os.environ.get("GEMINI_API_KEY")))
print("Key prefix:", os.environ.get("GEMINI_API_KEY")[:10] if os.environ.get("GEMINI_API_KEY") else "None")

models = ["gemini-1.5-flash", "gemini-1.0-pro", "gemini-pro"]
for model in models:
    try:
        print(f"Trying {model}...")
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.environ.get("GEMINI_API_KEY"),
            temperature=0.7
        )
        res = llm.invoke("ping")
        print(f"Success with {model}!", res)
        break
    except Exception as e:
        print(f"Failed with {model}. Error: {e}")
