FROM python:3.12-slim

ARG LDDC_REF=84631e8cd011fcc3f71ca0ae017e2c9758958ffc
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git ca-certificates curl \
        libdbus-1-3 libegl1 libgl1 libglib2.0-0 libxkbcommon0 \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/chenmozhijin/LDDC.git /opt/LDDC \
    && cd /opt/LDDC \
    && git checkout ${LDDC_REF} \
    && pip install --no-cache-dir . \
    && mkdir -p /licenses \
    && cp LICENSE /licenses/LDDC-GPL-3.0.txt \
    && rm -rf /opt/LDDC/.git

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

ENV PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=offscreen \
    XDG_CACHE_HOME=/data/cache \
    XDG_CONFIG_HOME=/data/config \
    LDDC_REF=${LDDC_REF}

HEALTHCHECK --interval=20s --timeout=5s --retries=10 \
    CMD curl -fsS http://127.0.0.1:8090/healthz || exit 1
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8090"]
