FROM python:3.13-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY requirements.txt .
# Install the CPU-only torch + torchvision build in its own step, from its
# own dedicated index — this app never touches a GPU, in this container or on
# Railway, and the default Linux torch wheel otherwise drags in ~800MB of
# unused nvidia-* packages. Installing it first (rather than combining
# indices on the main install) keeps the two indices from being resolved
# together, which otherwise blows up the resolver ("resolution-too-deep")
# given the loose version ranges elsewhere in requirements.txt. torch and
# torchvision MUST be pinned and installed together from the same index —
# resolving them separately/from different indices risks an ABI mismatch
# ("operator torchvision::nms does not exist") since torchvision is compiled
# against a specific torch build. --system installs into the image's system
# Python, matching how pip behaved here (no venv in this image).
RUN uv pip install --system --no-cache --index-url https://download.pytorch.org/whl/cpu torch==2.12.1 torchvision==0.27.1
RUN uv pip install --system --no-cache -r requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
CMD ["sh", "-c", "uvicorn src.api.server:app --host 0.0.0.0 --port ${PORT:-5000} --proxy-headers --forwarded-allow-ips='*'"]