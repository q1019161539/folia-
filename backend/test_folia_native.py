import unittest

from folia_native import FOLIA_EFFECT_MODES, FOLIA_RENDERER_REVISION, apply_folia_preview_profile, build_folia_config, normalized_folia_settings


class FoliaNativeTests(unittest.TestCase):
    def test_all_pinned_effects_are_exposed(self):
        self.assertEqual(len(FOLIA_EFFECT_MODES), 13)
        self.assertIn("sonnet", FOLIA_EFFECT_MODES)
        self.assertIn("diorama", FOLIA_EFFECT_MODES)

    def test_renderer_contract_forces_only_background_transparent(self):
        job = {
            "id": "abc",
            "title": "歌",
            "artist": "人",
            "alignment": {
                "offset_ms": 100,
                "lines": [{
                    "text": "你好",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "timing_precision": "forced-character",
                    "words": [
                        {"text": "你", "start_ms": 1000, "end_ms": 1400},
                        {"text": "好", "start_ms": 1400, "end_ms": 2000},
                    ],
                }],
            },
        }
        cfg = build_folia_config(job, {"mode": "sonnet", "visualizer_opacity": 0.75})
        self.assertTrue(cfg["background"]["transparent"])
        self.assertEqual(cfg["visualizerOpacity"], 0.75)
        self.assertEqual(cfg["lyrics"]["lines"][0]["startTime"], 1.1)
        self.assertEqual(cfg["lyrics"]["lines"][0]["words"][1]["endTime"], 2.1)

    def test_settings_are_pinned_and_bounded(self):
        cfg = normalized_folia_settings({"renderer_revision": "wrong", "mode": "wrong", "lyrics_font_scale": 99, "position_x": -8, "position_y": 108})
        self.assertEqual(cfg["renderer_revision"], FOLIA_RENDERER_REVISION)
        self.assertEqual(cfg["mode"], "classic")
        self.assertEqual(cfg["lyrics_font_scale"], 2.0)
        self.assertFalse(cfg["alpha_mov_audio"])
        self.assertEqual(cfg["position_x"], 0)
        self.assertEqual(cfg["position_y"], 100)

    def test_tempera_is_a_transparent_foreground_with_exact_primary(self):
        job = {"id": "tempera", "title": "标题", "artist": "歌手", "alignment": {"lines": []}}
        cfg = build_folia_config(job, {
            "mode": "tempera", "position_x": 42, "position_y": 68,
            "theme": {"primaryColor": "#ff3366"},
            "visualizer_tunings": {"tempera": {"showBlocks": True, "textInversion": True}},
        })
        self.assertIsNone(cfg["song"])
        self.assertFalse(cfg["visualizerTunings"]["tempera"]["showBlocks"])
        self.assertFalse(cfg["visualizerTunings"]["tempera"]["textInversion"])
        self.assertEqual(cfg["visualizerTunings"]["tempera"]["colorMode"], "duo")
        self.assertEqual(cfg["theme"]["primaryColor"], "#ff3366")
        # Tempera uses the contrast color as its secondary text face; the
        # renderer still forces the actual canvas background transparent.
        self.assertEqual(cfg["theme"]["backgroundColor"], "#ffffff")
        self.assertEqual(cfg["studioTransform"], {"x": 42, "y": 68})

    def test_sonnet_preview_is_lightweight_without_changing_export(self):
        job = {"id": "preview", "alignment": {"lines": [{"text": "歌词", "start_ms": 0, "end_ms": 1000}]}}
        export = build_folia_config(job, normalized_folia_settings({"mode": "sonnet"}))
        preview = apply_folia_preview_profile(export)
        self.assertNotIn("sonnet", export["visualizerTunings"])
        self.assertEqual(preview["previewProfile"], "balanced")
        self.assertFalse(preview["visualizerTunings"]["sonnet"]["showOnlyText"])
        self.assertEqual(preview["visualizerTunings"]["sonnet"]["textureResolution"], 0.75)
        self.assertFalse(preview["visualizerTunings"]["sonnet"]["postProcessEnabled"])

    def test_tempera_preview_reduces_gpu_cost(self):
        job = {"id": "preview", "alignment": {"lines": []}}
        export = build_folia_config(job, normalized_folia_settings({"mode": "tempera"}))
        preview = apply_folia_preview_profile(export)
        self.assertEqual(preview["visualizerTunings"]["tempera"]["textureResolution"], 0.5)
        self.assertFalse(preview["visualizerTunings"]["tempera"]["postProcessEnabled"])


if __name__ == "__main__":
    unittest.main()
