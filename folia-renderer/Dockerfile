FROM papersman/folia-web@sha256:27f36fe454eaa2af0ac8e53e7d2cb9694e6bad3a3ed1ad711b8e64086c0bf719

USER root
RUN apk add --no-cache chromium ffmpeg font-noto-cjk python3 py3-pip \
    && python3 -m venv /opt/folia-renderer \
    && /opt/folia-renderer/bin/pip install --no-cache-dir \
       fastapi==0.116.1 uvicorn[standard]==0.35.0 websocket-client==1.8.0 numpy==2.3.3
RUN apk add --no-cache xvfb tini

WORKDIR /renderer
COPY app.py ./app.py
ENV PATH="/opt/folia-renderer/bin:$PATH" \
    FOLIA_STATIC_ROOT=/usr/share/nginx/html \
    MEDIA_ROOT=/media/bililive \
    OUTPUT_ROOT=/output \
    RENDER_PORT=8091 \
    PYTHONUNBUFFERED=1
EXPOSE 8091
ENTRYPOINT []
CMD ["tini", "--", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091"]
