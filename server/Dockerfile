# Annotie Collab Relay — WebSocket relay sunucusu
FROM python:3.12-slim

WORKDIR /app

# Bağımlılıklar (sabit; requirements.txt değişse de çalışsın)
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" websockets

# Kaynak kodu kopyala
COPY . .

# Relay portu
EXPOSE 8765

# main.py uvicorn'u 0.0.0.0:8765'te başlatır
CMD ["python", "main.py"]
