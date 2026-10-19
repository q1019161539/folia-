#!/bin/sh
set -eu
cp /app/*.py .
cp /release/stage/backend/*.py .
trap 'tail -n 8 /release/regression.log' 0
python -m unittest test_cover_fallback \
 test_publish_v2.V2Tests.test_prompt_locks_face_but_not_pose \
 test_publish_v2.V2Tests.test_parentheses_removed_from_cover_metadata_not_identity_or_dedup \
 test_publish_v2.V2Tests.test_supplied_reference_bypasses_video_selection_not_identity \
 test_publish_v2.V2Tests.test_gemini_primary_first_attempt_cache_restart_and_budget \
 test_publish_v2.V2Tests.test_fallback_after_six_failures_persists_model_before_request_and_reuses_cache \
 test_publish_v2.V2Tests.test_gemini_primary_recovery_preserves_attempts_and_ten_request_cap > /release/regression.log 2>&1
