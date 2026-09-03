# Node кезеңі — public-сайттың 3D/scroll React-бумасын (web/) құрайды.
# server/ ешқашан осы бумаға тәуелді емес: build сәтсіз аяқталса да Python
# кезеңі бөлек жүреді, тек static/app/{main.js,main.css} жаңармайды.
FROM node:20-slim AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt /app/server/requirements.txt
COPY server/requirements-postgres.txt /app/server/requirements-postgres.txt
RUN pip install --no-cache-dir -r /app/server/requirements.txt -r /app/server/requirements-postgres.txt

COPY server /app/server
COPY core/__init__.py /app/core/__init__.py
COPY core/version.py /app/core/version.py
COPY --from=webbuild /web/dist/main.js /app/server/app/web/static/app/main.js
COPY --from=webbuild /web/dist/main.css /app/server/app/web/static/app/main.css
ENV PYTHONPATH=/app
RUN python -c "from server.app.main import app; print('import_ok', app.title)"

EXPOSE 8000
CMD ["python", "-m", "server.run"]
