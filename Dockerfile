# PWD Estimator — single container: FastAPI app + in-app Google Gemma 3 4B (llama.cpp, CPU) + private SearXNG.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    EST_DATA_DIR=/var/data SEARXNG_URL=http://127.0.0.1:8888 LLM_BACKEND=llamacpp
RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-deploy.txt ./
RUN pip install -r requirements.txt -r requirements-deploy.txt \
 && pip uninstall -y opencv-python && pip install opencv-python-headless \
 && pip install llama-cpp-python==0.3.36 --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# SearXNG (open-source metasearch), pinned commit, own virtualenv, only reachable inside the container
ARG SEARXNG_COMMIT=f4822b3
RUN git clone https://github.com/searxng/searxng.git /opt/searxng && cd /opt/searxng && git checkout ${SEARXNG_COMMIT} \
 && python -m venv /opt/searxng-venv && /opt/searxng-venv/bin/pip install -r requirements.txt

COPY . .
RUN chmod +x deploy/start.sh
EXPOSE 8000
CMD ["sh", "/app/deploy/start.sh"]
