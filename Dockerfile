FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
COPY server/requirements-postgres.txt /app/server/requirements-postgres.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt -r /app/server/requirements-postgres.txt

COPY server /app/server

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["sh", "-c", "uvicorn server.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
