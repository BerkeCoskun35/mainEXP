# ----------------------------
# Flask + PostgreSQL için Dockerfile (Python 3.11)
# ----------------------------
FROM python:3.11-slim

# Çalışma dizini oluştur
WORKDIR /app

# Gereksinimleri kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Proje dosyalarını kopyala
COPY . .

# Render, PORT ortam değişkenini zorunlu tutar
ENV PORT=10000
EXPOSE 10000

# Flask uygulamasını başlat
CMD ["gunicorn", "expOrigin-main.app:app"]
