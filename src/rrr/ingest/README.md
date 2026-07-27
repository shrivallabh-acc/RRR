# Ingest

Converts **RKT Program Metrics** HTML report exports into the `brain/*.json` snapshot
format consumed by the main assessment pipeline (ADR-0018).

---

## Module overview

| File | Purpose |
|---|---|
| `html_extractor.py` | `HTMLExtractor` — parses the `const __REPORT__` embedded JSON from RKT HTML files |
| `brain_writer.py` | `BrainWriter` — maps extracted records to the brain contract and appends to the history file |
| `_cli.py` | `rrr-ingest` Click entry point |
| `field_maps.py` | Static mappings from RKT field names to brain contract field names |

---

## How it works

RKT HTML reports contain a `const __REPORT__` JavaScript variable that embeds all
release data as a JSON object. The ingest pipeline:

1. Scans `--html-dir` for `.html` files.
2. `HTMLExtractor` finds `const __REPORT__` in each file, extracts and parses the JSON.
3. Extracts: story-point metrics, quality scores, E2E pass rates, defect counts,
   scope-creep history, environment data, dependency data, TOC value stream tag,
   programme code.
4. `BrainWriter` maps these to the brain contract and writes a dated snapshot entry to
   `<brain-dir>/<value-stream>-history.json`.
5. Upsert semantics: running the same file twice does not create duplicate entries.

---

## CLI

```
rrr-ingest [OPTIONS]

  --html-dir  PATH    (required) Directory containing RKT HTML export files
  --brain-dir PATH    (required) Output directory for brain JSON history files
  --value-stream TEXT (required) Value-stream name prefix for the output file
  --verbose           Enable DEBUG logging
```

```powershell
# Convert all HTML files in input/ to brain/OSM-history.json
rrr-ingest --html-dir input/ --brain-dir brain/ --value-stream "OSM"

# With debug logging
rrr-ingest --html-dir input/ --brain-dir brain/ --value-stream "OSM" --verbose
```

---

## Brain data contract

The output `<value-stream>-history.json` is a list of dated snapshots:

```json
[
  {
    "snapshot_date": "2026-06-08",
    "value_stream": "OSM",
    "releases": [
      {
        "ir_name": "RetirePlus RC/RCP Enrollment",
        "programme": "OSM",
        "toc_value_stream": "Retirement-Services",
        "story_points": { "planned": 120, "completed": 108, "velocity": 95 },
        "quality_score": 2.4,
        "e2e_pass_rate": 0.87,
        "defects": { "blocker": 0, "critical": 1, "major": 3, "minor": 12 },
        "environment": { ... },
        "dependencies": [ ... ]
      }
    ]
  }
]
```

See `src/rrr/tools/rkt_brain_reader.py` for the full read-side contract.

---

## Programmatic use

```python
from rrr.ingest import HTMLExtractor, BrainWriter
from pathlib import Path

extractor = HTMLExtractor()
writer = BrainWriter(brain_dir=Path("brain"), value_stream="OSM")

for html_file in Path("input").glob("*.html"):
    records = extractor.extract(html_file)
    writer.write(records)
```
