# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TRADER_DB=/app/runtime/trader.db
COPY requirements-app.txt ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir -r requirements-app.txt; else pip install --no-cache-dir -r requirements-app.txt; fi
COPY src ./src
COPY trader ./trader
COPY sample_data ./sample_data
RUN chmod -R a+rX /app && useradd --create-home --uid 10001 trader && mkdir -p /app/runtime && chown -R trader:trader /app/runtime
USER trader
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=3)"
CMD ["python", "-m", "uvicorn", "trader.api:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
