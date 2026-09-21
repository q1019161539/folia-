"""Patch the pinned Folia Tempera bundle with a foreground-safe text edge.

The renderer image is pinned by digest, so these guarded replacements target one
known minified asset. A changed upstream bundle must fail the image build instead
of silently patching the wrong code.
"""

from __future__ import annotations

from pathlib import Path


STATIC_ASSETS = Path("/usr/share/nginx/html/assets")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Tempera {label} patch expected one match, found {count}")
    return source.replace(old, new, 1)


def patch_bundle_text(source: str) -> str:
    source = replace_once(
        source,
        'style:new r({...o,fill:e.color??i.ink})',
        'style:new r({...o,fill:e.color??i.ink,stroke:{color:"#000000",width:Math.max(2,Math.min(4,e.fontSize*.035)),join:"round"}})',
        "outline",
    )
    source = replace_once(
        source,
        't.shadowEnabled&&(u=new n({text:e.char,style:new r({...o,fill:i.ink})})',
        't.shadowEnabled&&(u=new n({text:e.char,style:new r({...o,fill:"#000000"})})',
        "shadow colour",
    )
    return replace_once(
        source,
        'e.shadow.alpha=n.alpha*.34',
        'e.shadow.alpha=n.alpha*.55',
        "shadow opacity",
    )


def main() -> None:
    matches = []
    for path in STATIC_ASSETS.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        if "shadowEnabled" in text and "e.shadow.alpha=n.alpha*.34" in text:
            matches.append((path, text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one pinned Tempera bundle, found {len(matches)}")
    path, source = matches[0]
    patched = patch_bundle_text(source)
    path.write_text(patched, encoding="utf-8")
    print(f"Patched Tempera outline and shadow in {path.name}")


if __name__ == "__main__":
    main()
