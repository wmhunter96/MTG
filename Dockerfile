FROM python:3.12-slim
LABEL org.opencontainers.image.source=https://github.com/wmhunter96/MTG

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Settings + price/EDHREC cache live here
RUN mkdir -p /config

ENV CONFIG_PATH=/config/settings.yaml
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
