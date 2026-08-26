FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FREELLM_DATA_DIR=/data

WORKDIR /app
RUN useradd --create-home --uid 10001 freellm && mkdir -p /data && chown -R freellm:freellm /data /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=freellm:freellm app ./app
USER freellm
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
