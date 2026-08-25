import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.5-mini")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./radar.db")
