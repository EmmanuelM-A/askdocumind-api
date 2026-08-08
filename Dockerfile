FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
# --extra-index-url pulls the CPU-only torch build instead of the default CUDA
# build on Linux, which drags in ~800MB of unused nvidia-* packages — this app
# never touches a GPU, in this container or on Railway.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["sh", "-c", "uvicorn src.api.server:app --host 0.0.0.0 --port ${PORT:-5000} --proxy-headers --forwarded-allow-ips='*'"]