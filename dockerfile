FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2 + playwright
RUN apt-get update && apt-get install -y \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy RAG pipeline first (handlers.py imports from it)
COPY rag_pipeline/ ./rag_pipeline/

# Copy backend
COPY backend/ ./backend/

WORKDIR /app/backend

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]