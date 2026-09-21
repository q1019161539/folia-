import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from font_assets import BUILTIN_FONTS, list_fonts, store_font, validate_font_bytes


class _Name:
    nameID = 1
    def toUnicode(self): return "测试字体"


class _Font:
    def __getitem__(self, key): return type("Names", (), {"names": [_Name()]})()
    def close(self): pass


class FontAssetsTests(unittest.TestCase):
    def test_rejects_invalid_extension_and_header(self):
        with self.assertRaisesRegex(ValueError, "只支持"):
            validate_font_bytes("bad.zip", b"font")
        with self.assertRaisesRegex(ValueError, "文件头"):
            validate_font_bytes("bad.ttf", b"bad")

    @patch("font_assets.TTFont", return_value=_Font())
    def test_content_addressed_storage_and_deduplication(self, _):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            content = b"\x00\x01\x00\x00" + b"font payload"
            first = store_font(root, "font.ttf", "", content)
            second = store_font(root, "font.ttf", "", content)
            self.assertEqual(first["id"], second["id"])
            self.assertFalse(first["deduplicated"])
            self.assertTrue(second["deduplicated"])
            self.assertEqual(list_fonts(root)[:len(BUILTIN_FONTS)], BUILTIN_FONTS)
            self.assertEqual(list_fonts(root)[-1]["family"], "测试字体")


if __name__ == "__main__":
    unittest.main()
