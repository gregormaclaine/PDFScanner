import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY or OPENAI_API_KEY == "sk-xxxx":
    print("Error: OPENAI_API_KEY set but it seems to be still the placeholder.")
else:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        models = client.models.list()
        print("Available OpenAI Models for your API key:")
        for model in sorted([m.id for m in models.data]):
            print(f"- {model}")
    except Exception as e:
        print(f"Failed to fetch models: {str(e)}")
