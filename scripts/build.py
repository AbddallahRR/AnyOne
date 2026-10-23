"""Build script: bundles & minifies CSS and JS for production."""

import hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
HERE = Path(__file__).resolve().parent.parent
STATIC = HERE / "static"
DIST   = STATIC / "dist"

DIST.mkdir(parents=True, exist_ok=True)

BUILD_INFO = DIST / "build.json"

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, content: str):
    p.write_text(content, encoding="utf-8")

# ── CSS bundles ───────────────────────────────────────────────────────────
# Shared base files that are identical across all pages.
# Extracted into a single cached chunk to avoid re-downloading on navigation.
SHARED_CSS = ["inter.css", "fa-subset.css", "base.css", "layout.css"]

CSS_BUNDLES = {
    "index":    ["index.css"],
    "serie":    ["serie.css"],
    "reader":   ["reader.css"],
    "settings": ["settings.css"],
    "schedule": ["schedule.css"],
}

# ── JS bundles ────────────────────────────────────────────────────────────
JS_BUNDLES = {
    "index":    ["base.js", "toast.js", "confirm.js", "queue-indicator.js", "scraper-health.js", "notifications.js", "app.js"],
    "serie":    ["base.js", "toast.js", "confirm.js", "queue-indicator.js", "scraper-health.js", "notifications.js", "serie.js"],
    "reader":   ["base.js", "reader.js"],
    "settings": ["base.js", "toast.js", "confirm.js", "settings.js"],
    "schedule": ["base.js", "toast.js", "confirm.js", "queue-indicator.js", "scraper-health.js", "notifications.js", "schedule.js"],
}

try:
    from rcssmin import cssmin as minify_css
except ImportError:
    minify_css = lambda x: x
    print("  [WARN] rcssmin no instalado — CSS no se minificará")

try:
    from rjsmin import jsmin as minify_js
except ImportError:
    minify_js = lambda x: x
    print("  [WARN] rjsmin no instalado — JS no se minificará")

def bundle_css(name: str, sources: list[str]) -> tuple[str, str, bytes]:
    parts = []
    for src in sources:
        path = STATIC / "css" / src
        if not path.exists():
            print(f"  [WARN] CSS not found: {path}")
            continue
        parts.append(read(path))
    raw = "\n".join(parts)
    minified = minify_css(raw)
    raw_bytes = minified.encode("utf-8")
    h = hash_bytes(raw_bytes)
    out_name = f"{name}.{h}.css"
    out_path = DIST / out_name
    write(out_path, minified)
    print(f"  CSS {name}: {len(raw_bytes)//1024}KB → {out_name}")
    return out_name, name, raw_bytes

def bundle_js(name: str, sources: list[str]) -> tuple[str, str, bytes]:
    parts = []
    for src in sources:
        path = STATIC / "js" / src
        if not path.exists():
            print(f"  [WARN] JS not found: {path}")
            continue
        parts.append(read(path))
    raw = "\n".join(parts)
    minified = minify_js(raw)
    raw_bytes = minified.encode("utf-8")
    h = hash_bytes(raw_bytes)
    out_name = f"{name}.{h}.js"
    out_path = DIST / out_name
    write(out_path, minified)
    print(f"  JS  {name}: {len(raw_bytes)//1024}KB → {out_name}")
    return out_name, name, raw_bytes

def clean_dist():
    for f in DIST.iterdir():
        if f.is_file() and f.suffix in (".css", ".js", ".json"):
            f.unlink()

def main():
    print("=== Frontend Build ===")

    clean_dist()

    bundles = {}

    # Shared CSS chunk (fonts + base + layout) — cached once across all pages
    print("\n--- Shared CSS Chunk ---")
    out_name, _, _ = bundle_css("shared", SHARED_CSS)
    bundles["css:shared"] = out_name

    print("\n--- CSS Page Bundles ---")
    for name, sources in CSS_BUNDLES.items():
        out_name, _, _ = bundle_css(name, sources)
        bundles[f"css:{name}"] = out_name

    print("\n--- JS Bundles ---")
    for name, sources in JS_BUNDLES.items():
        out_name, _, _ = bundle_js(name, sources)
        bundles[f"js:{name}"] = out_name

    # Write manifest
    manifest = {
        "bundles": bundles,
        "version": 2,
    }
    write(BUILD_INFO, json.dumps(manifest, indent=2))
    print(f"\n✓ Manifest written to {BUILD_INFO}")

    total_size = sum(
        f.stat().st_size for f in DIST.iterdir() if f.suffix in (".css", ".js")
    )
    print(f"  Total bundle size: {total_size//1024}KB")

if __name__ == "__main__":
    main()
