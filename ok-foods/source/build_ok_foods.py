"""Render the OK Foods artifact into site/ as a self-contained page.

    python scripts/build_ok_foods.py [--offline] [--date YYYY-MM-DD]

Writes:
    site/index.html            the public library index
    site/ok-foods/index.html   the artifact, data embedded, no runtime fetch

The page is deliberately dependency-free: no CDN, no external stylesheet, no
runtime network call. It renders from a JSON blob embedded at build time, so it
works from a file:// URL, behind a firewall, and in an email preview pane.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import compute_margin

REPO = Path(__file__).resolve().parent.parent
SITE = REPO / "site"
TEMPLATES = Path(__file__).resolve().parent / "templates"

# The published page carries its own source: the reproducible half of the pipeline is copied
# into the site (see emit_source_bundle) and the page links there, relative. The artifact and
# its working repo are deliberately separate things and neither links to the other.
# NOTE: this file is itself published in that bundle. Nothing written in it is private.
SOURCE_URL = "source/"
PAGES_REPO_URL = "https://github.com/cameronhayes500-cmyk/cameronhayes500-cmyk.github.io"

# What a stranger needs to rebuild every number on the page from scratch, and nothing else.
BUNDLE_SCRIPTS = ["fetch_fred.py", "compute_margin.py", "build_ok_foods.py"]
BUNDLE_DATA = ["fred_PPOULTUSDM.csv", "fred_PMAIZMTUSDM.csv",
               "fred_PSMEAUSDM.csv", "fred_CPIAUCSL.csv", "ok_foods_payload.json"]

INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cameron Hayes — public-data work</title>
<meta name="description" content="Small working analyses built entirely from public data.">
<style>
:root{{color-scheme:light;--plane:#f9f9f7;--surface:#fcfcfb;--text:#0b0b0b;
 --text2:#52514e;--muted:#898781;--border:rgba(11,11,11,.10);--link:#2a78d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--text:#fff;--text2:#c3c2b7;--muted:#898781;
 --border:rgba(255,255,255,.10);--link:#3987e5}}}}
:root[data-theme="dark"]{{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;--text:#fff;
 --text2:#c3c2b7;--muted:#898781;--border:rgba(255,255,255,.10);--link:#3987e5}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--text);
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.6}}
.wrap{{max-width:720px;margin:0 auto;padding:64px 24px 96px}}
h1{{font-size:clamp(28px,5vw,40px);letter-spacing:-.02em;margin:0 0 14px;font-weight:640}}
.lede{{color:var(--text2);font-size:18px;margin:0 0 12px;max-width:60ch}}
.byline{{font-size:14px;color:var(--muted);border-top:1px solid var(--border);
 padding-top:16px;margin:28px 0 40px}}
a{{color:var(--link)}}
.card{{display:block;background:var(--surface);border:1px solid var(--border);
 border-radius:12px;padding:22px 24px;margin-bottom:16px;text-decoration:none;color:inherit}}
.card:hover{{border-color:var(--muted)}}
.card h2{{font-size:19px;margin:0 0 6px;font-weight:640;color:var(--link)}}
.card p{{margin:0;color:var(--text2);font-size:15px}}
.card .meta{{font-size:12.5px;color:var(--muted);margin-top:10px;
 text-transform:uppercase;letter-spacing:.07em;font-weight:600}}
footer{{margin-top:56px;padding-top:20px;border-top:1px solid var(--border);
 font-size:13.5px;color:var(--muted)}}
</style>
</head>
<body><div class="wrap">
<h1>Public-data work</h1>
<p class="lede">Small working analyses, each built entirely from public sources — no proprietary
feeds, no company systems, no credentials. Every one ships its own scripts and its own raw data,
so it is reproducible end to end, and every number links back to the series it came from.</p>
<p class="byline">Cameron Hayes ·
<a href="mailto:cameronhayes500@gmail.com">cameronhayes500@gmail.com</a> ·
<a href="{repo_url}">source</a></p>

<a class="card" href="ok-foods/">
  <h2>Broiler margin over grain</h2>
  <p>Benchmark poultry price minus the corn and soybean-meal cost of a pound of sellable
  chicken, monthly since 2003, with the margin decomposed into its price and feed sides
  and a measured lead time between them.</p>
  <div class="meta">Poultry · IMF benchmark series · updated {updated}</div>
</a>

<footer>Built {updated}. Each page states its own method and its own limits.</footer>
</div></body></html>
"""


SOURCE_INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Broiler margin over grain — source and data</title>
<style>
:root{{color-scheme:light;--plane:#f9f9f7;--surface:#fcfcfb;--text:#0b0b0b;
 --text2:#52514e;--muted:#898781;--border:rgba(11,11,11,.10);--link:#2a78d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;
 --plane:#0d0d0d;--surface:#1a1a19;--text:#fff;--text2:#c3c2b7;--muted:#898781;
 --border:rgba(255,255,255,.10);--link:#3987e5}}}}
:root[data-theme="dark"]{{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;--text:#fff;
 --text2:#c3c2b7;--muted:#898781;--border:rgba(255,255,255,.10);--link:#3987e5}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--text);
 font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.6}}
.wrap{{max-width:720px;margin:0 auto;padding:56px 24px 80px}}
h1{{font-size:26px;letter-spacing:-.02em;margin:0 0 12px;font-weight:640}}
h2{{font-size:15px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
 margin:34px 0 10px;font-weight:640}}
p{{color:var(--text2);max-width:64ch}}
a{{color:var(--link)}}
ul{{list-style:none;padding:0;margin:0}}
li{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
 padding:12px 16px;margin-bottom:8px}}
li .n{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:14px}}
li .d{{display:block;font-size:14px;color:var(--text2);margin-top:2px}}
pre{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
 padding:14px 16px;overflow-x:auto;font-size:14px}}
footer{{margin-top:44px;padding-top:18px;border-top:1px solid var(--border);
 font-size:13.5px;color:var(--muted)}}
</style>
</head>
<body><div class="wrap">
<h1>Source and data — broiler margin over grain</h1>
<p>Everything behind <a href="../">the chart</a>: the three scripts that fetch, compute and
render it, and the raw series exactly as they were downloaded. No API key, no login, no
proprietary feed. Rebuilt from these files, the page reproduces number for number.</p>

<h2>Scripts</h2>
<ul>
<li><a class="n" href="fetch_fred.py">fetch_fred.py</a>
  <span class="d">Downloads the four FRED series to CSV. Every later step runs offline from them.</span></li>
<li><a class="n" href="compute_margin.py">compute_margin.py</a>
  <span class="d">Joins the series on calendar month, applies the ration / feed-conversion /
  dressing-yield assumptions, deflates by CPI, and writes the payload.</span></li>
<li><a class="n" href="build_ok_foods.py">build_ok_foods.py</a>
  <span class="d">Renders the payload into the single self-contained page.</span></li>
</ul>

<h2>Data, as downloaded</h2>
<ul>
<li><a class="n" href="fred_PPOULTUSDM.csv">fred_PPOULTUSDM.csv</a>
  <span class="d">IMF global poultry benchmark, US cents per lb.</span></li>
<li><a class="n" href="fred_PMAIZMTUSDM.csv">fred_PMAIZMTUSDM.csv</a>
  <span class="d">IMF maize, US dollars per tonne.</span></li>
<li><a class="n" href="fred_PSMEAUSDM.csv">fred_PSMEAUSDM.csv</a>
  <span class="d">IMF soybean meal, US dollars per tonne.</span></li>
<li><a class="n" href="fred_CPIAUCSL.csv">fred_CPIAUCSL.csv</a>
  <span class="d">BLS CPI-U, used only to state the series in constant dollars.</span></li>
<li><a class="n" href="ok_foods_payload.json">ok_foods_payload.json</a>
  <span class="d">The computed series the page is drawn from — the intermediate, so the
  arithmetic can be checked without running anything.</span></li>
</ul>

<h2>Rebuild</h2>
<pre>python fetch_fred.py          # or skip it and use the CSVs here
python compute_margin.py
python build_ok_foods.py --offline</pre>

<footer>Cameron Hayes ·
<a href="mailto:cameronhayes500@gmail.com">cameronhayes500@gmail.com</a> ·
built {updated}</footer>
</div></body></html>
"""


def emit_source_bundle(out_dir: Path, updated: str) -> int:
    """Copy the reproducible half of the pipeline into the published site.

    The page claims every number is checkable; that claim is only true if the reader can
    reach the code and the raw series, so the bundle travels with the artifact itself.

    Everything listed in BUNDLE_SCRIPTS / BUNDLE_DATA becomes public the moment this runs.
    Add nothing here without reading it first.
    """
    src = out_dir / "source"
    src.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    n = 0
    for name in BUNDLE_SCRIPTS:
        shutil.copyfile(here / name, src / name)
        n += 1
    for name in BUNDLE_DATA:
        f = REPO / "data" / name
        if f.exists():
            shutil.copyfile(f, src / name)
            n += 1
    (src / "index.html").write_text(SOURCE_INDEX.format(updated=updated), encoding="utf-8")
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--date", default=None, help="override the stamped build date")
    args = ap.parse_args()

    payload = compute_margin.build(offline=args.offline)

    stamp = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    updated = stamp.strftime("%d %B %Y").lstrip("0")

    tpl = (TEMPLATES / "ok_foods.html").read_text(encoding="utf-8")
    html = (tpl
            .replace("{{PAYLOAD}}", json.dumps(payload, separators=(",", ":")))
            .replace("{{UPDATED}}", updated)
            .replace("{{NMONTHS}}", str(payload["coverage"]["n"]))
            .replace("{{LAST_MONTH}}", payload["coverage"]["last"])
            .replace("{{REPO_URL}}", SOURCE_URL))

    out_dir = SITE / "ok-foods"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (SITE / "index.html").write_text(
        INDEX.format(repo_url=PAGES_REPO_URL, updated=updated), encoding="utf-8")
    # GitHub Pages: serve the files as-is, no Jekyll pass.
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    nfiles = emit_source_bundle(out_dir, updated)

    size = (out_dir / "index.html").stat().st_size
    print(f"  site/ok-foods/index.html   {size/1024:.0f} KB   "
          f"{payload['coverage']['n']} months through {payload['coverage']['last']}")
    print(f"  site/ok-foods/source/      {nfiles} files + index")
    print(f"  site/index.html            library index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
