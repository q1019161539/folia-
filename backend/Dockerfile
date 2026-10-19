FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py asr_matching.py standard_timeline.py word_timeline.py automation.py automation_runtime.py song_analysis.py folia_native.py folia_upstream.py font_assets.py image_assets.py song_identity.py song_identity_diagnostics.py pipeline_eta.py ai_slot.py recording_metadata.py recorder_identity.py publishing.py cover_frames.py cover_fallback.py publish_v2.py title_generation.py render_revisions.py performance_gate.py sqlite_runtime.py .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8000"]
