# cameronhayes500-cmyk.github.io

Small working analyses, each built entirely from public data — no proprietary feeds, no company
systems, no credentials. Live at **https://cameronhayes500-cmyk.github.io/**

Every page states its own method and its own limits, links every number back to the public series
it came from, and ships as a single self-contained HTML file with no external dependencies: no
CDN, no runtime network call, no tracking. Each one opens from `file://` and works offline.

## Pages

| Page | What it is | Sources |
|---|---|---|
| [`/ok-foods/`](https://cameronhayes500-cmyk.github.io/ok-foods/) | **Broiler margin over grain** — benchmark poultry price minus the corn and soybean-meal cost of a pound of sellable chicken, monthly since 2003, decomposed into its price and feed sides with a measured lead time between them | IMF benchmark series via FRED: `PPOULTUSDM`, `PMAIZMTUSDM`, `PSMEAUSDM` |

## Build

These pages are rendered by a small stdlib-only Python pipeline (fetch → compute → render) that
lives in a separate repository. This repository holds only the rendered output, so the pages stay
publishable independently of the tooling that produces them.

---

Cameron Hayes · <cameronhayes500@gmail.com>
