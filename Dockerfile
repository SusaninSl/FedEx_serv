FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# системні залежності, якщо раптом щось треба зібрати
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# ставимо Python-залежності
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# каталоги для БД і етикеток
RUN mkdir -p /data /storage/labels

# копіюємо код
COPY app ./app

# дефолтні (можна перекривати в Portainer)
ENV DATABASE_URL=sqlite:////data/app.db \
    FEDEX_BASE_URL=https://apis-sandbox.fedex.com \
    SERVICE_TOKEN=change-me

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
