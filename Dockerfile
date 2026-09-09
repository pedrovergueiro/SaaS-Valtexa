# Imagem da plataforma. Sem Keras/TensorFlow: a inferência é um serviço à parte
# (VALTEXA-B), consumido por HTTP. É o que mantém esta imagem em poucas centenas
# de MB e permite escalar a API sem GPU.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# As dependências primeiro: a camada só é reconstruída quando elas mudam.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY valtexa ./valtexa
COPY simulator ./simulator
COPY pyproject.toml README.md ./

# Usuário sem privilégios: um processo comprometido não deve poder escrever no
# próprio código.
RUN useradd --create-home --uid 10001 valtexa \
    && mkdir -p /app/storage \
    && chown -R valtexa:valtexa /app
USER valtexa

EXPOSE 8080

# /health responde enquanto o processo estiver de pé e informa, no corpo, se o
# banco e a inferência estão acessíveis — liveness e readiness separados.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "valtexa.main:app", "--host", "0.0.0.0", "--port", "8080"]
