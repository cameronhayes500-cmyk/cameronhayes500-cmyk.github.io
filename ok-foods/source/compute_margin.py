"""Compute the broiler margin-over-grain series and its diagnostics.

Emits data/ok_foods_payload.json, consumed by scripts/build_ok_foods.py.

WHAT THIS MEASURES, stated precisely so nobody over-reads it:

  margin_over_grain ($/lb) = benchmark poultry price ($/lb)
                           - (corn + soybean meal) cost per lb of sellable chicken

It is an INDICATOR OF DIRECTION AND COMPRESSION, not a cost accounting figure.
It deliberately excludes:
  - the ~10% of ration weight that is fats, minerals, vitamins and amino acids
  - processing, labor, energy, freight, chick cost and grower pay
  - the basis between IMF global benchmarks and US delivered cash prices,
    which is real and makes the level here sit BELOW a US processor's true cost

Because corn and soybean meal drive nearly all of the VARIANCE in ration cost,
the series tracks margin movement well even though it does not price the level.

    python scripts/compute_margin.py [--offline]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import fetch_fred

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

LB_PER_MT = 2204.62

# Defaults are industry-typical and are exposed as adjustable inputs on the page,
# so the reader can substitute their own operating numbers rather than trust ours.
DEFAULTS = {
    "corn_pct": 0.60,       # share of ration by weight
    "sbm_pct": 0.30,        # share of ration by weight
    "fcr": 1.85,            # lb feed per lb live weight
    "yield_pct": 0.75,      # live weight -> ready-to-cook weight
}


def monthly_index(obs: list[tuple[str, float]]) -> dict[str, float]:
    return {d: v for d, v in obs}


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def log_change(series: list[float], k: int) -> list[float | None]:
    """k-month log change, None where undefined or non-positive."""
    out: list[float | None] = [None] * len(series)
    for i in range(k, len(series)):
        a, b = series[i - k], series[i]
        if a and b and a > 0 and b > 0:
            out[i] = math.log(b / a)
    return out


def lag_profile(feed: list[float], poultry: list[float], k: int, max_lag: int = 18):
    """Correlate k-month log change in poultry[t] against feed[t-lag]."""
    dp = log_change(poultry, k)
    df = log_change(feed, k)
    rows = []
    for lag in range(0, max_lag + 1):
        xs, ys = [], []
        for t in range(len(dp)):
            if t - lag < 0:
                continue
            a, b = df[t - lag], dp[t]
            if a is None or b is None:
                continue
            xs.append(a)
            ys.append(b)
        rows.append({"lag": lag, "r": pearson(xs, ys) if len(xs) >= 12 else None, "n": len(xs)})
    return rows


def percentile_of(value: float, population: list[float]) -> float:
    below = sum(1 for v in population if v < value)
    return 100.0 * below / len(population)


def build(offline: bool = False) -> dict:
    poultry = monthly_index(fetch_fred.load("PPOULTUSDM", offline))
    corn = monthly_index(fetch_fred.load("PMAIZMTUSDM", offline))
    sbm = monthly_index(fetch_fred.load("PSMEAUSDM", offline))
    cpi = monthly_index(fetch_fred.load("CPIAUCSL", offline))

    months = sorted(set(poultry) & set(corn) & set(sbm) & set(cpi))
    if not months:
        raise RuntimeError("no overlapping months across the series")

    d = DEFAULTS
    ration_lb_per_lb_rtc = d["fcr"] / d["yield_pct"]

    cpi_base = cpi[months[-1]]          # everything expressed in latest-month dollars

    rows = []
    for m in months:
        # grain contribution to one metric ton of complete ration
        grain_per_mt_ration = d["corn_pct"] * corn[m] + d["sbm_pct"] * sbm[m]
        grain_per_lb_ration = grain_per_mt_ration / LB_PER_MT
        grain_per_lb_rtc = grain_per_lb_ration * ration_lb_per_lb_rtc
        poultry_usd_lb = poultry[m] / 100.0
        rows.append({
            "month": m,
            "poultry_usd_lb": round(poultry_usd_lb, 5),
            "corn_usd_mt": round(corn[m], 3),
            "sbm_usd_mt": round(sbm[m], 3),
            "grain_usd_lb": round(grain_per_lb_rtc, 5),
            "margin_usd_lb": round(poultry_usd_lb - grain_per_lb_rtc, 5),
            "deflator": round(cpi_base / cpi[m], 6),
        })

    margins = [r["margin_usd_lb"] for r in rows]
    real_margins = [r["margin_usd_lb"] * r["deflator"] for r in rows]
    poultry_s = [r["poultry_usd_lb"] for r in rows]
    grain_s = [r["grain_usd_lb"] for r in rows]

    # Index the lookback by CALENDAR MONTH, not by row offset. The joined series has holes
    # (a month is kept only if every source publishes it), and a row offset silently lands on
    # the wrong date - which labelled a 13-month window as 12 until this was caught.
    def m_idx(m: str) -> int:
        return int(m[:4]) * 12 + int(m[5:7]) - 1

    def nearest(target: int) -> int:
        return min(range(len(months)), key=lambda i: abs(m_idx(months[i]) - target))

    i0 = nearest(m_idx(months[-1]) - 12)
    window_months = m_idx(months[-1]) - m_idx(months[i0])
    gaps = [m for a, b in zip(months, months[1:])
            for m in (f"{(m_idx(a)+k)//12:04d}-{(m_idx(a)+k) % 12 + 1:02d}"
                      for k in range(1, m_idx(b) - m_idx(a)))]

    latest, prior12 = rows[-1], rows[i0]
    d_margin = latest["margin_usd_lb"] - prior12["margin_usd_lb"]
    d_price = latest["poultry_usd_lb"] - prior12["poultry_usd_lb"]
    d_grain = -(latest["grain_usd_lb"] - prior12["grain_usd_lb"])  # cost down = margin up

    # The same decomposition in constant dollars. Over a 12-month window the deflator drift is
    # small, so this is a robustness check rather than a different answer.
    rd_margin = real_margins[-1] - real_margins[i0]
    rd_price = (latest["poultry_usd_lb"] * latest["deflator"]
                - rows[i0]["poultry_usd_lb"] * rows[i0]["deflator"])
    rd_grain = -(latest["grain_usd_lb"] * latest["deflator"]
                 - rows[i0]["grain_usd_lb"] * rows[i0]["deflator"])

    win = 120  # trailing ten years — the horizon that removes most of the deflation question
    recent_real = real_margins[-win:] if len(real_margins) >= win else real_margins

    lag12 = lag_profile(grain_s, poultry_s, k=12)
    lag3 = lag_profile(grain_s, poultry_s, k=3)
    scored = [r for r in lag12 if r["r"] is not None]
    peak = max(scored, key=lambda r: r["r"]) if scored else None

    # forward read: where has feed cost moved over the last `peak_lag` months, and
    # what has historically followed in the poultry price at that lag
    horizon = peak["lag"] if peak else 0
    recent_feed_move = None
    if horizon and len(grain_s) > horizon:
        a, b = grain_s[-1 - horizon], grain_s[-1]
        if a > 0:
            recent_feed_move = (b / a) - 1.0

    return {
        "generated_from": "public data only; no company systems, credentials or private sources",
        "series_meta": fetch_fred.SERIES,
        "defaults": d,
        "ration_lb_per_lb_rtc": round(ration_lb_per_lb_rtc, 4),
        "coverage": {"first": months[0], "last": months[-1], "n": len(months),
                     "missing_months": gaps},
        "rows": rows,
        "latest": latest,
        "stats": {
            "margin_min": min(margins),
            "margin_max": max(margins),
            "margin_mean": sum(margins) / len(margins),
            "margin_percentile_now": percentile_of(latest["margin_usd_lb"], margins),
            # Constant-dollar versions. The nominal percentile above overstates the rank because
            # it ranks 2003 dollars against 2026 dollars; these are the honest numbers.
            "real": {
                "now": real_margins[-1],
                "mean": sum(real_margins) / len(real_margins),
                "min": min(real_margins),
                "max": max(real_margins),
                "percentile_full": percentile_of(real_margins[-1], real_margins),
                "percentile_recent": percentile_of(real_margins[-1], recent_real),
                "recent_window_months": len(recent_real),
                "recent_mean": sum(recent_real) / len(recent_real),
                "base_month": months[-1],
            },
            "yoy": {
                "from_month": prior12["month"],
                "window_months": window_months,
                "d_margin": d_margin,
                "from_price": d_price,
                "from_grain_cost": d_grain,
                "real_d_margin": rd_margin,
                "real_from_price": rd_price,
                "real_from_grain_cost": rd_grain,
            },
        },
        "lag": {
            "profile_12m": lag12,
            "profile_3m": lag3,
            "peak": peak,
            "recent_feed_move_over_horizon": recent_feed_move,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    payload = build(offline=args.offline)
    DATA.mkdir(exist_ok=True)
    out = DATA / "ok_foods_payload.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    c, s, lat = payload["coverage"], payload["stats"], payload["latest"]
    print(f"coverage      {c['first']} .. {c['last']}  ({c['n']} months)")
    print(f"latest        poultry ${lat['poultry_usd_lb']:.3f}/lb  "
          f"grain ${lat['grain_usd_lb']:.3f}/lb  margin ${lat['margin_usd_lb']:.3f}/lb")
    print(f"margin range  ${s['margin_min']:.3f} .. ${s['margin_max']:.3f}  "
          f"mean ${s['margin_mean']:.3f}")
    r = s["real"]
    print(f"percentile    nominal {s['margin_percentile_now']:.0f}th  |  "
          f"REAL {r['percentile_full']:.0f}th full history  |  "
          f"REAL {r['percentile_recent']:.0f}th vs last {r['recent_window_months']} months")
    print(f"real margin   ${r['now']:.3f} (in {r['base_month']} dollars)  "
          f"full-mean ${r['mean']:.3f}  recent-mean ${r['recent_mean']:.3f}")
    y = s["yoy"]
    print(f"12m change    margin {y['d_margin']:+.3f} = price {y['from_price']:+.3f} "
          f"+ grain-cost {y['from_grain_cost']:+.3f}")
    print(f"12m real      margin {y['real_d_margin']:+.3f} = price {y['real_from_price']:+.3f} "
          f"+ grain-cost {y['real_from_grain_cost']:+.3f}")
    pk = payload["lag"]["peak"]
    if pk:
        print(f"peak lag      {pk['lag']} months  r={pk['r']:.3f}  n={pk['n']}")
    print("lag profile   " + "  ".join(
        f"{r['lag']}:{r['r']:.2f}" for r in payload["lag"]["profile_12m"] if r["r"] is not None))
    print(f"3m-change check " + "  ".join(
        f"{r['lag']}:{r['r']:.2f}" for r in payload["lag"]["profile_3m"][:13] if r["r"] is not None))
    fm = payload["lag"]["recent_feed_move_over_horizon"]
    if fm is not None:
        print(f"feed move over horizon  {fm*100:+.1f}%")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
