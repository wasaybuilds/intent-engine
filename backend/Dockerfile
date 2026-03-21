# Playwright base image includes Chromium + all Linux system dependencies
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies (playwright version aligned with base image)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Browsers are pre-installed in the Playwright image — no `playwright install` needed
COPY app ./app

EXPOSE 8000

# Default command: FastAPI web server (override for Celery worker in compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
