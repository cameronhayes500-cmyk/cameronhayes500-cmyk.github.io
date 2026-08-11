"""Fetch and cache the public price series behind the OK Foods artifact.

Sources are all public, no API key, no credentials, nothing owned by any company.
Raw CSVs are cached under data/ so the artifact is reproducible offline and the
gate never needs network.

    python scripts/fetch_fred.py            # refresh cache
    python scripts/fetch_fred.py --offline  # fail if cache is missing, never fetch

Series (each verified against its FRED page before being wired in here):

  PPOULTUSDM   Global price of Poultry        U.S. cents per pound   IMF   monthly
  PMAIZMTUSDM  Global price of Corn           U.S. dollars per m.t.  IMF   monthly
  PSMEAUSDM    Global price of Soybean Meal   U.S. dollars per m.t.  IMF   monthly

Deliberately NOT wired in: WPU01830131 and WPU012202 (BLS PPI). Both return data,
but FRED's metadata endpoint is blocked from here and the titles could not be
confirmed. Per the repo rule, an unverified source is dropped, not guessed.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

SERIES = {
    "PPOULTUSDM": {
        "title": "Global price of Poultry",
        "units": "U.S. cents per pound",
        "source": "International Monetary Fund via FRED",
        "note": "IMF benchmark poultry (whole-bird) spot price. Benchmark prices are "
                "representative of the global market and determined by the largest "
                "exporter of the commodity; period averages in nominal U.S. dollars.",
    },
    "PMAIZMTUSDM": {
        "title": "Global price of Corn",
        "units": "U.S. dollars per metric ton",
        "source": "International Monetary Fund via FRED",
        "note": "IMF benchmark corn price, period average, nominal U.S. dollars.",
    },
    "PSMEAUSDM": {
        "title": "Global price of Soybean Meal",
        "units": "U.S. dollars per metric ton",
        "source": "International Monetary Fund via FRED",
        "note": "IMF benchmark soybean meal price, period average, nominal U.S. dollars.",
    },
    "CPIAUCSL": {
        "title": "Consumer Price Index for All Urban Consumers: All Items",
        "units": "Index 1982-1984 = 100, seasonally adjusted",
        "source": "U.S. Bureau of Labor Statistics via FRED",
        "note": "Used only as a deflator, to state the spread in constant dollars. Without it "
                "a 23-year percentile rank mostly measures the currency rather than the margin.",
    },
}

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
UA = {"User-Agent": "Mozilla/5.0 (public-data artifact; cameronhayes500@gmail.com)"}


def cache_path(sid: str) -> Path:
    return DATA / f"fred_{sid}.csv"


def fetch(sid: str, timeout: int = 30) -> str:
    req = urllib.request.Request(CSV_URL.format(sid=sid), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"{sid}: HTTP {r.status}")
        return r.read().decode("utf-8", "replace")


def parse(text: str, sid: str) -> list[tuple[str, float]]:
    """FRED CSV -> [(YYYY-MM, value)]. Missing values are '.' and are dropped."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2:
        raise RuntimeError(f"{sid}: unexpected CSV shape")
    out: list[tuple[str, float]] = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        date, raw = r[0].strip(), r[1].strip()
        if not date or raw in (".", ""):
            continue
        try:
            out.append((date[:7], float(raw)))
        except ValueError:
            continue
    if not out:
        raise RuntimeError(f"{sid}: no usable observations")
    return out


def load(sid: str, offline: bool = False) -> list[tuple[str, float]]:
    """Cached-first read. Refreshes the cache unless --offline."""
    p = cache_path(sid)
    if not offline:
        try:
            text = fetch(sid)
            parse(text, sid)  # validate before overwriting a good cache
            DATA.mkdir(exist_ok=True)
            p.write_text(text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001 - network is best-effort
            if not p.exists():
                raise
            print(f"  ! {sid}: fetch failed ({type(e).__name__}), using cache", file=sys.stderr)
    if not p.exists():
        raise RuntimeError(f"{sid}: no cache at {p} and offline mode requested")
    return parse(p.read_text(encoding="utf-8"), sid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="never fetch; require cache")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    for sid, meta in SERIES.items():
        obs = load(sid, offline=args.offline)
        print(f"  {sid:<12} {meta['title']:<30} n={len(obs):<5} "
              f"{obs[0][0]} .. {obs[-1][0]}  last={obs[-1][1]:.2f} {meta['units']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
