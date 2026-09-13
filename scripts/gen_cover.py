"""Cover image generator for blogs and templates.

Every published artifact gets its OWN cover; borrowing another post's image
misrepresents the content and erodes trust (learned in production). This
renders a styled HTML card and screenshots it with headless Chrome.

Usage:
  python3 gen_cover.py blog <out.png> --title "..." --tag "For CPAs" --accent "#7C3AED" \
      [--brand FinBoard --brand-accent Board --site finboard.ai/blog --byline "FinBoard Team"]

Chrome binary: $CHROME_BIN, else the macOS default path.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

BLOG_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;width:1200px;height:630px;background:#F5F0E8;font-family:'Inter',-apple-system,sans-serif;color:#0A0A0A;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;position:relative}}
.motif{{position:absolute;right:-70px;bottom:-70px;width:460px;height:340px;opacity:.10;transform:rotate(-6deg)}}
.motif div{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}
.motif span{{height:44px;border-radius:6px;background:{accent}}}
.top{{display:flex;justify-content:space-between;align-items:center;padding:44px 56px 0}}
.logo{{font-size:26px;font-weight:800}}.logo b{{color:#2563EB}}
.chip{{font-size:15px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:{accent};border:2px solid {accent}44;background:{accent}11;padding:9px 20px;border-radius:999px}}
.mid{{padding:0 56px;display:flex;align-items:center;gap:14px}}
.signal{{width:18px;height:18px;border-radius:50%;background:{accent};box-shadow:32px 0 0 {accent}66,64px 0 0 {accent}22}}
.flow{{height:4px;width:320px;border-radius:99px;background:linear-gradient(90deg,{accent},transparent)}}
.bot{{display:flex;justify-content:space-between;align-items:center;padding:0 56px 42px;font-size:16px;color:rgba(10,10,10,.5)}}
.rule{{height:5px;background:{accent};width:96px;border-radius:99px;margin-bottom:18px}}
</style></head><body>
<div class="motif"><div>{cells}</div></div>
<div class="top"><div class="logo">{brand_pre}<b>{brand_accent}</b></div><div class="chip">{tag}</div></div>
<div class="mid"><div class="rule"></div><div class="signal"></div><div class="flow"></div></div>
<div class="bot"><span>{site}</span><span>{byline}</span></div>
</body></html>"""


def build_html(title: str, tag: str, accent: str, brand: str = "FinBoard",
               brand_accent: str = "Board", site: str = "finboard.ai/blog",
               byline: str = "FinBoard Team") -> str:
    """Pure HTML build (testable without Chrome)."""
    brand_pre = brand[: len(brand) - len(brand_accent)] if brand.endswith(brand_accent) else brand
    return BLOG_HTML.format(
        tag=tag, accent=accent,
        cells="<span></span>" * 20,
        brand_pre=brand_pre, brand_accent=brand_accent, site=site, byline=byline,
    )


def render(html: str, out_path: str | Path, width: int = 1200, height: int = 630) -> None:
    chrome = os.environ.get("CHROME_BIN", DEFAULT_CHROME)
    if not Path(chrome).exists():
        raise RuntimeError(f"Chrome not found at {chrome}; set CHROME_BIN")
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        src = f.name
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", f"--screenshot={out_path}",
             f"--window-size={width},{height}", "--hide-scrollbars", f"file://{src}"],
            capture_output=True, check=True, timeout=60,
        )
    finally:
        os.unlink(src)
    if not Path(out_path).exists():
        raise RuntimeError(f"Chrome produced no screenshot at {out_path}")


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["blog"], help="cover style")
    parser.add_argument("out", help="output .png path")
    parser.add_argument("--title", required=True)
    parser.add_argument("--tag", required=True, help="chip label, e.g. 'For CPAs'")
    parser.add_argument("--accent", required=True, help="hex accent, e.g. '#7C3AED'")
    parser.add_argument("--brand", default="FinBoard")
    parser.add_argument("--brand-accent", default="Board")
    parser.add_argument("--site", default="finboard.ai/blog")
    parser.add_argument("--byline", default="FinBoard Team")
    args = parser.parse_args(argv[1:])
    html = build_html(args.title, args.tag, args.accent, args.brand,
                      args.brand_accent, args.site, args.byline)
    render(html, args.out)
    print(f"cover written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
