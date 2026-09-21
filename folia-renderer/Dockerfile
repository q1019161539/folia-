FROM node:24-alpine AS folia-builder
ARG FOLIA_REVISION=80c073490482303d4283d1d5205be7707c96179d
RUN apk add --no-cache git python3
WORKDIR /src
RUN git init \
    && git remote add origin https://github.com/chthollyphile/folia-major.git \
    && git fetch --depth=1 origin "$FOLIA_REVISION" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$FOLIA_REVISION"
COPY patch_upstream_source.py /tmp/patch_upstream_source.py
RUN python3 /tmp/patch_upstream_source.py /src "$FOLIA_REVISION"
RUN npm ci --no-audit --no-fund \
    && VERCEL_GIT_COMMIT_SHA="$FOLIA_REVISION" DOCKER_STACK_VERSION=1.0.26 npm run build

FROM alpine:3.22

USER root
RUN apk add --no-cache chromium ffmpeg font-noto-cjk python3 py3-pip \
    && python3 -m venv /opt/folia-renderer \
    && /opt/folia-renderer/bin/pip install --no-cache-dir \
       fastapi==0.116.1 uvicorn[standard]==0.35.0 websocket-client==1.8.0 numpy==2.3.3
RUN apk add --no-cache xvfb tini

WORKDIR /renderer
COPY --from=folia-builder /src/dist /usr/share/nginx/html
COPY app.py ./app.py
COPY folia-version.json ./folia-version.json
ENV PATH="/opt/folia-renderer/bin:$PATH" \
    FOLIA_STATIC_ROOT=/usr/share/nginx/html \
    MEDIA_ROOT=/media/bililive \
    OUTPUT_ROOT=/output \
    RENDER_PORT=8091 \
    PYTHONUNBUFFERED=1
EXPOSE 8091
ENTRYPOINT []
CMD ["tini", "--", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091"]
