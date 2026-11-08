import os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
candidates = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]
for name in candidates:
    for attempt in range(2):
        try:
            r = client.models.generate_content(model=name, contents="Chào bạn, trả lời đúng 5 từ.")
            print("OK  ", name, "->", (r.text or "").strip()[:60])
            break
        except Exception as e:
            msg = f"{type(e).__name__} {str(e)[:90]}"
            if "503" in msg and attempt == 0:
                time.sleep(3)
                continue
            print("LOI ", name, "->", msg)
            break