import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL   = "gpt-4o-mini"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:%23nandhu%402003%23@db.xgicfjqgzqimdqtsetkq.supabase.co:5432/postgres")

# Scraping
TARGET_URL = os.getenv("TARGET_URL", "https://getalchemystai.com/")
MAX_PAGES  = int(os.getenv("MAX_PAGES", 100))

# Chunking
CHUNK_SIZE    = 500   # tokens per chunk
CHUNK_OVERLAP = 50    # token overlap between adjacent chunks

# Embeddings
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM   = 1536

# Retrieval
TOP_K = 5  # number of chunks to retrieve per query

# LLM
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_TOKENS   = 1024
