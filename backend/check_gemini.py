import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
from google import genai

key = os.environ.get("GEMINI_API_KEY")
model = os.environ.get("GEMINI_MODEL")
print("Co key:", bool(key), "| do dai key:", len(key or ""), "| model:", model)

client = genai.Client(api_key=key)
try:
    r = client.models.generate_content(model=model, contents="Xin chào, trả lời một câu ngắn.")
    print("OK:", r.text)
except Exception as e:
    print("LOI:", type(e).__name__, str(e)[:400])
    print("--- Cac model flash kha dung ---")
    try:
        for m in client.models.list():
            if "flash" in m.name.lower():
                print(m.name)
    except Exception as e2:
        print("Khong liet ke duoc:", type(e2).__name__, str(e2)[:200])