import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-26b-a4b-it")


def main():
    client = genai.Client()  # GEMINI_API_KEY を環境変数から読み込む
    response = client.models.generate_content(
        model=MODEL,
        contents="Roses are red...",
    )
    print(response.text)


if __name__ == "__main__":
    main()
