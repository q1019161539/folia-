#!/bin/sh
set -eu
cp /app/*.py .
cp /stage/backend/*.py .
cp /stage/backend/Dockerfile .
trap 'tail -n 10 /logs/regression.log' 0
python -m unittest test_cover_fallback test_publish_v2 test_publishing test_title_generation test_sqlite_runtime test_collection_client test_render_revisions test_performance_gate > /logs/regression.log 2>&1
