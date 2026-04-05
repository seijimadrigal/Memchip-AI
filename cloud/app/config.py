"""Configuration from environment variables."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://memchip:memchip@postgres:5432/memchip")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "postgresql://memchip:memchip@postgres:5432/memchip")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Rate limiting
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", "10000"))
