import os

# ─── Telegram Bot (от @BotFather) ─────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8986948715:AAFJ_N3zqsCu5FvoN-hgsxSAkBxFFdsyKc8")

# ─── OpenRouter / Нейросеть ──────────────────────────────────
AI_API_KEY = os.getenv("AI_API_KEY", "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")
AI_MODEL = os.getenv("AI_MODEL", "nvidia/nemotron-3-ultra-8b")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "300"))

# ─── Настройки ──────────────────────────────────────────────
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
REMINDER_MINUTES = int(os.getenv("REMINDER_MINUTES", "60"))
DIGEST_TIME = os.getenv("DIGEST_TIME", "09:00")
DB_PATH = os.getenv("DB_PATH", "tasks.db")
