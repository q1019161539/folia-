FROM folia-video-studio-studio-api:cover-prompt-20261012
WORKDIR /app
COPY backend/publishing.py backend/publish_v2.py ./
