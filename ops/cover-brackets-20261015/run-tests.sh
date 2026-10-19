#!/bin/sh
set -eu
cp /app/*.py .
cp /release/stage/backend/*.py .
cp /release/stage/backend/Dockerfile .
trap 'tail -n 8 /release/regression.log' 0
python -m unittest test_cover_fallback test_publish_v2 test_publishing test_title_generation test_sqlite_runtime test_collection_client test_render_revisions test_performance_gate > /release/regression.log 2>&1
