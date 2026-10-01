FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY src/ ./src/
RUN mkdir -p data logs resumes

ENV PORT=5000
EXPOSE 5000

# One worker: the JSON-file store and per-process SECRET_KEY fallback assume a single process
CMD gunicorn -w 1 --threads 4 --timeout 180 -b 0.0.0.0:${PORT} main:app
