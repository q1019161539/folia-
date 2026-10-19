import json
import tempfile
import unittest
from pathlib import Path

import httpx
from PIL import Image

from publishing import (
    BUILTIN_COVER_FONTS,
    BililiveToolClient,
    PublishPrepareError,
    PublishRetryableError,
    PublishSettings,
    build_description,
    build_payload,
    build_tags,
    build_title,
    choose_cover_template,
    map_to_bililive_path,
    merge_preset_config,
    preset_description_template,
    render_cover,
    retry_delay_seconds,
    stable_template_index,
    streamer_from_source,
    validate_cover_font,
)


APP = Path(__file__).with_name("app.py").read_text(encoding="utf-8")


def settings(root: Path) -> PublishSettings:
    return PublishSettings(
        enabled=True,
        auto_publish_enabled=False,
        bililive_base_url="http://bililive.test/api",
        bililive_passkey="not-saved-in-payload",
        bililive_uid=181647901,
        bililive_preset_id="s9iw1rmff2",
        output_root=(root / "output").resolve(),
        output_legacy_root=(root / "output-legacy").resolve(),
        bililive_output_root=Path("/app/Folia成片"),
        bililive_output_legacy_root=Path("/app/历史Folia成片"),
        cover_template_root=(root / "templates").resolve(),
        cover_output_root=(root / "output/publish/covers").resolve(),
    )


class MetadataTest(unittest.TestCase):
    def test_deterministic_metadata(self):
        self.assertEqual(build_title("芒芒_Mou", "离人赋"), "芒芒_Mou《离人赋》｜直播翻唱")
        self.assertEqual(
            build_description("芒芒_Mou", "离人赋", "云汐").splitlines()[:3],
            ["主播：芒芒_Mou", "曲目：《离人赋》", "原唱/歌手：云汐"],
        )
        self.assertEqual(build_tags("芒芒_Mou", "离人赋", "云汐"), ["芒芒_Mou", "离人赋", "云汐", "直播翻唱", "翻唱"])

    def test_identity_is_required_and_not_replaced(self):
        with self.assertRaises(PublishPrepareError):
            build_title("芒芒_Mou", "")
        create = APP.split("def ensure_publish_job", 1)[1].split("def reconcile_publish_jobs", 1)[0]
        self.assertIn("project.get('identified_title')", create)
        self.assertIn("project.get('identified_artist')", create)
        for forbidden in ("matched_title", "manual_title", "project.get('title')", "song.get('title')"):
            self.assertNotIn(forbidden, create)

    def test_long_title_never_truncates_song_identity(self):
        song = "非常长的歌名" * 7
        value = build_title("一个也很长的主播名", song)
        self.assertIn(f"《{song}》", value)
        self.assertLessEqual(len(value), 80)

    def test_streamer_uses_renderer_path_rule(self):
        self.assertEqual(streamer_from_source("bilibili/芒芒_Mou/2026/a.mp4"), "芒芒_Mou")
        self.assertEqual(streamer_from_source("小红泡-管珩心/2026/a.mp4"), "小红泡-管珩心")


class CoverTest(unittest.TestCase):
    def test_template_choice_is_stable_for_streamer_and_song(self):
        first = stable_template_index("芒芒_Mou", "离人赋", 4)
        self.assertEqual(first, stable_template_index("芒芒_Mou", "离人赋", 4))
        self.assertNotEqual(
            hashlib_key("芒芒_Mou", "离人赋"),
            hashlib_key("小红泡-管珩心", "离人赋"),
        )

    def test_cover_is_1920_by_1080_and_source_video_survives(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "covers/01.jpg"
            source.parent.mkdir(parents=True)
            Image.new("RGB", (1200, 1200), (60, 90, 130)).save(source)
            video = root / "output/song.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"original-mp4")
            template = choose_cover_template([source], "芒芒_Mou", "离人赋")
            cover = render_cover(template, root / "output/publish/covers/job.jpg", "离人赋", "芒芒_Mou")
            with Image.open(cover) as image:
                self.assertEqual(image.size, (1920, 1080))
                self.assertEqual(image.format, "JPEG")
            self.assertEqual(video.read_bytes(), b"original-mp4")

    def test_streamer_without_covers_fails_with_actionable_message(self):
        with self.assertRaises(PublishPrepareError) as raised:
            choose_cover_template([], "赛蒂娅Sentia", "b")
        self.assertIn("赛蒂娅Sentia", str(raised.exception))
        self.assertIn("投稿管理", str(raised.exception))

    def test_cover_font_choice_is_applied_and_bad_font_is_reported(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "01.png"
            Image.new("RGB", (1920, 1080), (60, 90, 130)).save(source)
            serif = render_cover(source, root / "serif.jpg", "离人赋", "芒芒_Mou", BUILTIN_COVER_FONTS["builtin-serif"])
            sans = render_cover(source, root / "sans.jpg", "离人赋", "芒芒_Mou", BUILTIN_COVER_FONTS["builtin-sans"])
            self.assertNotEqual(serif.read_bytes(), sans.read_bytes())
            broken = root / "broken.ttf"
            broken.write_bytes(b"not a font")
            with self.assertRaises(PublishPrepareError):
                render_cover(source, root / "broken.jpg", "离人赋", "芒芒_Mou", (str(broken), 0))
            with self.assertRaises(PublishPrepareError):
                validate_cover_font((str(broken), 0))
            validate_cover_font(BUILTIN_COVER_FONTS["builtin-serif"])


def hashlib_key(streamer: str, title: str) -> bytes:
    import hashlib
    return hashlib.sha256((streamer + "\0" + title).encode()).digest()


class PathAndPayloadTest(unittest.TestCase):
    def test_current_and_legacy_paths_are_mapped_without_copying(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); cfg = settings(root)
            current = cfg.output_root / "a/song.mp4"; current.parent.mkdir(parents=True); current.touch()
            legacy = cfg.output_legacy_root / "b/song.mp4"; legacy.parent.mkdir(parents=True); legacy.touch()
            self.assertEqual(map_to_bililive_path(current, cfg), "/app/Folia成片/a/song.mp4")
            self.assertEqual(map_to_bililive_path(legacy, cfg), "/app/历史Folia成片/b/song.mp4")
            with self.assertRaises(PublishPrepareError):
                map_to_bililive_path(root / "elsewhere/song.mp4", cfg)

    def test_preset_policy_is_preserved_and_only_owned_fields_change(self):
        preset = {"config": {"title": "old", "desc": "old", "tag": ["old"], "cover": "old", "tid": 138, "human_type2": 1003, "copyright": 1}}
        description = preset_description_template(preset, "fallback")
        merged = merge_preset_config(preset, "new", description, ["tag"], "/app/Folia成片/cover.jpg")
        self.assertEqual((merged["tid"], merged["human_type2"], merged["copyright"]), (138, 1003, 1))
        self.assertEqual((merged["title"], merged["desc"], merged["tag"], merged["cover"]), ("new", "old", ["tag"], "/app/Folia成片/cover.jpg"))
        self.assertEqual(preset["config"]["title"], "old")

    def test_empty_preset_description_uses_deterministic_fallback(self):
        self.assertEqual(preset_description_template({"config": {"desc": "", "tid": 138}}, "fallback"), "fallback")

    def test_payload_shape_contains_no_secret_or_source_delete(self):
        payload = build_payload(181647901, "/app/Folia成片/a.mp4", "离人赋", {"title": "t"})
        self.assertEqual(payload["videos"], [{"path": "/app/Folia成片/a.mp4", "title": "离人赋"}])
        self.assertEqual(payload["options"], {"removeOriginAfterUploadCheck": False})
        self.assertNotIn("passkey", json.dumps(payload).lower())
        v2 = Path(__file__).with_name("publish_v2.py").read_text(encoding="utf-8")
        self.assertIn('if self.settings.auto_publish_enabled',v2)
        self.assertIn('pipeline_version=2',v2)


class ClientTest(unittest.TestCase):
    def test_real_318_request_contract(self):
        requests = []
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/preset/video"):
                return httpx.Response(200, json=[{"id": "s9iw1rmff2", "name": "芒芒_Mou", "config": {"tid": 138}}])
            if request.url.path.endswith("/preset/video/s9iw1rmff2"):
                return httpx.Response(200, json={"id": "s9iw1rmff2", "config": {"tid": 138}})
            if request.url.path.endswith("/bili/formatDesc"):
                return httpx.Response(200, text="主播主页和 2026.09.27")
            if request.url.path.endswith("/bili/validUploadParams"):
                return httpx.Response(200, text="success")
            return httpx.Response(404)
        client = BililiveToolClient("http://test/api", "secret", transport=httpx.MockTransport(handler))
        try:
            presets = client.list_video_presets()
            preset = client.get_video_preset("s9iw1rmff2")
            description = client.format_description("主页 {{now}}", {"username": "芒芒_Mou"})
            result = client.validate_upload_config({"tid": preset["config"]["tid"]})
        finally:
            client.close()
        self.assertEqual(result, {"status_code": 200, "body": "success"})
        self.assertEqual(presets[0]["name"], "芒芒_Mou")
        self.assertEqual(description, "主播主页和 2026.09.27")
        self.assertEqual(requests[0].headers["authorization"], "secret")
        self.assertEqual(json.loads(requests[3].content), {"tid": 138})

    def test_validation_error_is_terminal_and_server_error_retries(self):
        terminal = BililiveToolClient("http://test/api", "x", transport=httpx.MockTransport(lambda request: httpx.Response(400, text="title required")))
        with self.assertRaises(PublishPrepareError): terminal.validate_upload_config({})
        terminal.close()
        retryable = BililiveToolClient("http://test/api", "x", transport=httpx.MockTransport(lambda request: httpx.Response(503, text="later")))
        with self.assertRaises(PublishRetryableError): retryable.get_video_preset("p")
        retryable.close()
        self.assertEqual(retry_delay_seconds(1), 60)
        self.assertEqual(retry_delay_seconds(10), 3600)


class PersistenceContractTest(unittest.TestCase):
    def test_automation_profile_locks_streamer_and_bililive_preset(self):
        self.assertIn("ALTER TABLE automation_profiles ADD COLUMN publish_streamer", APP)
        self.assertIn("ALTER TABLE automation_profiles ADD COLUMN bililive_preset_id", APP)
        create = APP.split("def create_automation_profile", 1)[1].split("def update_automation_profile", 1)[0]
        self.assertIn("publish_streamer,bililive_preset_id,bililive_preset_name", create)
        handoff = APP.split("def ensure_publish_job", 1)[1].split("def reconcile_publish_jobs", 1)[0]
        v2 = Path(__file__).with_name('publish_v2.py').read_text(encoding='utf-8')
        self.assertIn("profile.get('publish_streamer')", v2)
        self.assertIn("profile.get('bililive_preset_id')", v2)
        self.assertIn("未绑定主播投稿模板", v2)
        self.assertNotIn("or PUBLISH_SETTINGS.bililive_preset_id", handoff)
        update = APP.split("def update_automation_profile", 1)[1].split("\n@app.", 1)[0]
        for route in (create, update):
            self.assertNotIn("PUBLISH_SETTINGS.bililive_preset_id", route)

    def test_prepare_uses_streamer_covers_and_font(self):
        prepare = APP.split("def prepare_publish_job", 1)[1].split("def publish_worker_loop", 1)[0]
        self.assertIn("profile_cover_paths(profile['id'])", prepare)
        self.assertIn("cover_font_spec(profile.get('cover_font_id'))", prepare)
        self.assertIn("ALTER TABLE automation_profiles ADD COLUMN cover_font_id", APP)

    def test_font_delete_refuses_builtin_and_used_fonts(self):
        delete = APP.split("def delete_font", 1)[1].split("\n@app.", 1)[0]
        self.assertIn("'builtin-'", delete)
        self.assertIn("font_usages(font_id)", delete)
        usages = APP.split("def font_usages", 1)[1].split("\n@app.", 1)[0]
        self.assertIn("FROM jobs WHERE style LIKE", usages)
        self.assertIn("cover_font_id=?", usages)

    def test_source_job_is_unique_and_inserts_name_columns(self):
        schema = APP.split("CREATE TABLE IF NOT EXISTS publish_jobs", 1)[1].split("''')", 1)[0]
        self.assertIn("source_job_id TEXT NOT NULL UNIQUE", schema)
        self.assertIn("INSERT OR IGNORE INTO publish_jobs(", APP)
        self.assertIn("id,source_job_id,automation_run_id", APP)

    def test_restart_and_completed_jobs_do_not_create_duplicate_preparation(self):
        startup = APP.split("def startup()", 1)[1].split("@app.get('/healthz')", 1)[0]
        self.assertIn("WHERE status='preparing'", startup)
        reconcile = APP.split("def reconcile_publish_rows", 1)[1].split("def reconcile_publish_jobs", 1)[0]
        self.assertIn("WHERE source_job_id=?", reconcile)
        self.assertNotIn("submitting", reconcile)
        self.assertNotIn("uploading", reconcile)

    def test_reconciliation_has_a_durable_watermark_and_manual_backfill_is_bounded(self):
        automatic = APP.split("def reconcile_publish_jobs", 1)[1].split("def backfill_recent_publish_jobs", 1)[0]
        self.assertIn("publish_reconcile_since", automatic)
        self.assertIn("updated_at>=? AND updated_at<=?", automatic)
        manual = APP.split("def backfill_recent_publish_jobs", 1)[1].split("def prepare_publish_job", 1)[0]
        self.assertIn("min(int(limit),2)", manual)

    def test_phase_one_worker_stops_at_ready(self):
        worker = APP.split("def prepare_publish_job", 1)[1].split("def publish_worker_loop", 1)[0]
        self.assertIn("status='ready'", worker)
        self.assertNotIn("/bili/upload", worker)
        self.assertNotIn("bililive_task_id=", worker)


if __name__ == "__main__":
    unittest.main()
