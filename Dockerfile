FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
COPY server/requirements-postgres.txt /app/server/requirements-postgres.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt -r /app/server/requirements-postgres.txt

COPY server /app/server
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && sed -i 's/\r$//' /app/start.sh

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["/app/start.sh"]
