FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    HOST=0.0.0.0 \
    PORT=5001

WORKDIR /app

# CPU-only torch and torchvision first, from their own index, so
# sentence-transformers doesn't pull the much larger CUDA build
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.12.1 torchvision==0.27.1

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the reranker model into the image so startup doesn't download it.
# Keep this in step with RERANKER_MODEL_NAME.
ARG RERANKER_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANKER_MODEL_NAME}')"

COPY alembic.ini .
COPY alembic ./alembic
COPY src ./src

RUN useradd --create-home --uid 1000 app \
    && mkdir -p logs \
    && chown -R app:app /app
USER app

EXPOSE 5001

CMD ["python", "-m", "src.server"]
