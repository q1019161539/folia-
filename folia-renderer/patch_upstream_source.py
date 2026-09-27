from __future__ import annotations

import argparse
from pathlib import Path

EXPECTED_REVISION = "9cf822015328e47ee5e22061213010a70b4ec5c9"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"upstream patch guard failed for {path}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def apply(root: Path, revision: str) -> None:
    if revision != EXPECTED_REVISION:
        raise RuntimeError(f"unsupported Folia revision: {revision}")
    replace_once(
        root / "src/types.ts",
        "  fontWeight?: number;\n  animationIntensity:",
        "  fontWeight?: number;\n"
        "  studioTextOutline?: { enabled: boolean; width_px: number; color: string; scope: 'primary' };\n"
        "  studioFontAssetUrl?: string;\n  animationIntensity:",
    )

    shell = root / "src/components/visualizer/VisualizerShell.tsx"
    replace_once(shell, "import { getSizedCoverUrl } from '../../utils/coverUrl';\n", "import { getSizedCoverUrl } from '../../utils/coverUrl';\nimport { activateStudioTextOutline } from '../../utils/studioTextOutline';\n")
    replace_once(shell, "    const isBackButtonVisible = sharedProps?.alwaysShowBackButton || showBackButton;\n", "    const isBackButtonVisible = sharedProps?.alwaysShowBackButton || showBackButton;\n\n    useEffect(() => { activateStudioTextOutline(theme); }, [theme.studioTextOutline]);\n")

    obs = root / "src/components/obs/ObsBrowserSourceApp.tsx"
    replace_once(obs, "import { buildObsBrowserSourceConfigSignature, resolveObsBrowserSourceClockTime } from '../../utils/obsBrowserSource';\n", "import { buildObsBrowserSourceConfigSignature, resolveObsBrowserSourceClockTime } from '../../utils/obsBrowserSource';\nimport { setStudioPrimaryLyrics } from '../../utils/studioTextOutline';\n")
    replace_once(obs, "const EMPTY_SPECTRUM = new Uint8Array(0);\n", """const EMPTY_SPECTRUM = new Uint8Array(0);

const loadStudioFont = async (nextConfig: ObsBrowserSourceConfig): Promise<ObsBrowserSourceConfig> => {
    const url = nextConfig.theme.studioFontAssetUrl;
    const family = nextConfig.theme.fontFamily;
    if (!url || !family) { document.documentElement.dataset.studioFontReady = '1'; return nextConfig; }
    try {
        const loaded = await new FontFace(family, `url(${JSON.stringify(url)})`).load();
        document.fonts.add(loaded); await document.fonts.ready;
        document.documentElement.dataset.studioFontReady = '1';
        delete document.documentElement.dataset.studioFontError;
        return nextConfig;
    } catch {
        document.documentElement.dataset.studioFontReady = '1';
        document.documentElement.dataset.studioFontError = '1';
        return { ...nextConfig, theme: { ...nextConfig.theme, fontStyle: 'sans', fontFamily: 'Noto Sans CJK SC', studioFontAssetUrl: undefined } };
    }
};
""")
    replace_once(obs, """            const nextConfig = JSON.parse((event as MessageEvent).data) as ObsBrowserSourceConfig;
            const nextSignature = buildObsBrowserSourceConfigSignature(nextConfig);
            if (nextSignature === configSignatureRef.current) return;
            configSignatureRef.current = nextSignature;
            setConfig(nextConfig);
""", """            const receivedConfig = JSON.parse((event as MessageEvent).data) as ObsBrowserSourceConfig;
            const nextSignature = buildObsBrowserSourceConfigSignature(receivedConfig);
            if (nextSignature === configSignatureRef.current) return;
            configSignatureRef.current = nextSignature;
            setStudioPrimaryLyrics(receivedConfig.lyrics.lines.map(line => line.fullText));
            delete document.documentElement.dataset.studioFontReady;
            void loadStudioFont(receivedConfig).then(nextConfig => setConfig(nextConfig));
""")

    helper = root / "src/utils/studioTextOutline.ts"
    if helper.exists():
        raise RuntimeError(f"upstream unexpectedly contains {helper}")
    helper.write_text("""import type { Theme } from '../types';
type OutlineState = { enabled: boolean; width: number; color: string };
const disabled: OutlineState = { enabled: false, width: 0, color: '#000000' };
let active: OutlineState = disabled;
let canvasPatched = false;
let observer: MutationObserver | null = null;
let primaryTokens = new Set<string>();
const isPrimaryText = (text: string) => primaryTokens.has(text.trim());
export const setStudioPrimaryLyrics = (lines: string[]) => {
    primaryTokens = new Set(lines.flatMap(line => [line, ...Array.from(line), ...line.split(/\s+/)]).map(value => value.trim()).filter(Boolean));
};
export const resolveStudioTextOutline = (theme: Theme): OutlineState => {
    const raw = theme.studioTextOutline;
    if (!raw?.enabled || raw.scope !== 'primary') return disabled;
    const width = Math.max(0, Math.min(12, Number(raw.width_px) || 0));
    const color = /^#[0-9a-f]{6}$/i.test(raw.color ?? '') ? raw.color : '#000000';
    return { enabled: width > 0, width, color };
};
const installCanvasPatch = () => {
    if (canvasPatched || typeof CanvasRenderingContext2D === 'undefined') return;
    canvasPatched = true;
    const originalFillText = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function(text, x, y, maxWidth) {
        if (active.enabled && isPrimaryText(text) && this.canvas.width > 2 && this.canvas.height > 2) {
            this.save(); this.strokeStyle = active.color; this.lineWidth = active.width * 2;
            this.lineJoin = 'round'; this.miterLimit = 2;
            maxWidth === undefined ? this.strokeText(text, x, y) : this.strokeText(text, x, y, maxWidth);
            this.restore();
        }
        maxWidth === undefined ? originalFillText.call(this, text, x, y) : originalFillText.call(this, text, x, y, maxWidth);
    };
};
const applyDomOutline = () => {
    document.querySelectorAll<HTMLElement>('[data-studio-primary-outline]').forEach(node => {
        delete node.dataset.studioPrimaryOutline; node.style.webkitTextStroke = ''; node.style.paintOrder = '';
    });
    if (!active.enabled) return;
    document.querySelectorAll<HTMLElement>('#root *').forEach(node => {
        if (node.children.length || !isPrimaryText(node.textContent ?? '')) return;
        node.dataset.studioPrimaryOutline = '1';
        node.style.webkitTextStroke = `${active.width}px ${active.color}`;
        node.style.paintOrder = 'stroke fill';
    });
};
export const activateStudioTextOutline = (theme: Theme) => {
    installCanvasPatch(); active = resolveStudioTextOutline(theme); applyDomOutline();
    if (!observer) { observer = new MutationObserver(applyDomOutline); observer.observe(document.documentElement, { childList: true, characterData: true, subtree: true }); }
};
""", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("revision")
    args = parser.parse_args()
    apply(args.root, args.revision)
