# PWD Estimator — container for Railway (or any Docker host).
# The app, its vision models and the rate data. The Gemma assistant is OFF by default here (it needs ~3 GB RAM);
# set LLM_BACKEND=llamacpp and PWD_SKIP_LLM=0 as build/runtime variables on a large plan to turn it on.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    EST_DATA_DIR=/data TN_WEB_REFRESH=0 LLM_BACKEND=none EST_NO_DOTENV=1
ARG PWD_SKIP_LLM=1

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
# server OpenCV without display libraries (some dependencies pull the desktop build)
RUN pip install -r requirements.txt \
 && pip uninstall -y opencv-python opencv-contrib-python || true \
 && pip install --force-reinstall --no-deps opencv-python-headless

COPY . .
# large model files: a host may check out only Git LFS placeholders — download the real files (SHA-256 checked);
# if YOLOv8m cannot be fetched the app falls back to YOLOv8s
RUN PWD_SKIP_LLM=${PWD_SKIP_LLM} python -c "import sys; sys.path.insert(0, 'tools'); import setup_local as s; s.fetch_large_files()" || true \
 && if [ "${PWD_SKIP_LLM}" != "1" ]; then pip install llama-cpp-python==0.3.36 --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu; fi

EXPOSE 8000
CMD ["sh", "-c", "mkdir -p ${EST_DATA_DIR} && exec python -m uvicorn app:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT:-8000}"]
