"""Generate clearly marked, non-production Phase 1 cover backgrounds."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PALETTES = [
    ((48, 70, 112), (113, 151, 189)),
    ((87, 58, 105), (191, 120, 150)),
    ((39, 91, 87), (113, 177, 143)),
    ((91, 64, 46), (196, 143, 90)),
]


def main() -> None:
    output = Path(__file__).with_name("generic")
    output.mkdir(parents=True, exist_ok=True)
    for index, (top, bottom) in enumerate(PALETTES, 1):
        image = Image.new("RGB", (1920, 1080))
        pixels = image.load()
        for y in range(1080):
            ratio = y / 1079
            color = tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom))
            for x in range(1920):
                pixels[x, y] = color
        draw = ImageDraw.Draw(image)
        draw.rectangle((35, 35, 1885, 1045), outline=(255, 255, 255), width=3)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 42)
        except OSError:
            font = ImageFont.load_default(size=42)
        label = "PHASE 1 PLACEHOLDER - REPLACE BEFORE AUTO PUBLISH"
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(((1920 - box[2]) // 2, 990), label, font=font, fill=(255, 255, 255))
        image.save(output / f"placeholder-{index:02d}.jpg", "JPEG", quality=90)


if __name__ == "__main__":
    main()
