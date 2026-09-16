FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    HUGGINGFACE_HUB_CACHE=/models/huggingface/hub \
    TORCH_HOME=/models/torch \
    XDG_CACHE_HOME=/models/cache \
    OMP_NUM_THREADS=10 \
    MKL_NUM_THREADS=10 \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ffmpeg libsndfile1 sox ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.8.0 torchaudio==2.8.0 \
    && python -m pip install -r requirements.txt

COPY app ./app
COPY main.py .
COPY web.py .
COPY web ./web

EXPOSE 8080
CMD ["python", "web.py"]
