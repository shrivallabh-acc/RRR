# ADR-0021: TOC-Based Value-Stream Tagging During Ingest

**Status:** Accepted (implemented 2026-06-28)

## Context

The RKT Program Metrics HTML report carries two independent grouping signals:

1. **Programme code** — encoded in `ir_name` (e.g. `AIMS - ...`, `(ME&Q)`, `R5 ...`).
   Captures *who builds* the release (which engineering programme owns it).

2. **Table of Contents (TOC), Slide 2** — groups every release under a named business
   value stream (e.g. *Account Management*, *Education & Advice*, *Tech Foundation*).
   Captures *what user journey* the release serves.

These two signals are not interchangeable.  A release with `programme = "OSM"` may belong
to *Account Management*, *Education & Advice*, or any other value stream depending on its
business purpose — the programme code alone cannot answer "which value stream is this for?"

Before ADR-0021, the Trends tab used a programme-code-based classification
(`vs_category()`: direct / dependency / supporting / other) to group releases.  This
produced correct counts (22 Direct for OSM) but the groupings had no business-domain
meaning — "Direct" is a technical programme relationship, not a business value stream.

The TOC is already the authoritative release-grouping artefact in the RKT report; it is
maintained by the Programme Management Office and is the grouping logic used in planning
presentations (Slide 2 of the report).

## Decision

Parse the TOC section of the HTML during `rrr-ingest` and tag each release with its
canonical `toc_value_stream` name (e.g. `"Account Management"`) as a new optional field
on `ReleaseRecord`.  This field is:

- written to `brain/<vs>-history.json` alongside all other release metrics
- used by the Trends tab for the VS filter (replacing programme-code-based buttons)
- absent (`null`) for old brain files ingested before this ADR, which degrade gracefully
  to an "Untagged" bucket in the UI

### Parsing strategy

The TOC slide is identified by `data-ribbon="Table of Contents"` on a `<div class="page">`.
Within it, `toc-vs-label` elements name each value stream and the following
`toc-releases li a` elements list the releases under that VS.  We parse line by line with
compiled regexes (no DOM library) consistent with how `HTMLExtractor` reads `__REPORT__`.

Release names in the TOC are HTML-link text that may contain entities (`&amp;`).  We
HTML-unescape and normalise whitespace before looking up against `ir_name` so the match
is robust to minor formatting differences.

### Affected modules

| Module | Change |
|--------|--------|
| `src/rrr/models/brain.py` | Add `toc_value_stream: str \| None = None` to `ReleaseRecord` |
| `src/rrr/ingest/html_extractor.py` | Add `_parse_toc()` + `_normalize_name()`; inject field in `_map_release()` |
| `src/rrr/tools/brain_reader.py` | Add `list_toc_value_streams()` method |
| `src/rrr/ui/app.py` | Replace programme-category filter in Trends with TOC VS buttons |

`BrainWriter` is not changed — it writes whatever dict `HTMLExtractor` returns.

## Consequences

**Enables:**
- Trends tab filter buttons show the real business value-stream names from the TOC.
- `list_toc_value_streams()` lets callers discover VS names from the brain file without
  parsing the HTML again.
- Old brain files load without error (`InputContract` ignores missing fields; default `null`).

**Forecloses:**
- Historical brain files produce `toc_value_stream: null` until re-ingested — the UI
  places them in an "Untagged" bucket.  This is a one-time gap: re-running `rrr-ingest`
  against the same HTML files repopulates the field.

**Trade-off accepted:**
- An additional regex pass over the HTML (≈ 6 kB TOC section of a 2.3 MB file) is
  negligible; ingest is a once-per-week batch operation, not a hot path.

**Relation to other ADRs:**
- ADR-0012 defines `ReleaseRecord` as an `InputContract` (`extra=ignore`), making the
  new field backward-compatible.
- ADR-0018 defines the `HTMLExtractor` parsing approach (regex, not DOM); this ADR
  extends the same approach to the TOC section.
- ADR-0020 defines the NiceGUI dashboard; the Trends tab change is covered here.

## Implementation note

Implemented 2026-06-28.  7 TOC value streams extracted from the OSM programme report:
*Account Management, Distribution, Education & Advice, Engagement & Decisions,
Institutional Servicing, Offer Selection & Management, Tech Foundation.*
"Offer Selection & Management" contains only 2 releases (RetirePlus-family);
the majority of OSM-coded releases live under *Account Management* and *Education & Advice*.
