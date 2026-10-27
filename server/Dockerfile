# Annotie Collab Relay — WebSocket relay sunucusu
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kaynak kodu kopyala
COPY . .

# Root olmadan çalış
RUN useradd --system --uid 10001 relay
USER relay

# Relay portu
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)"

# main.py uvicorn'u 0.0.0.0:8765'te başlatır (konteyner içi; dış erişim compose'da)
CMD ["python", "main.py"]
