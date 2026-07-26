"""HTML ingest layer — extracts RKT Program Metrics HTML into brain contract JSON (ADR-0018).

Entry point for callers: ``HTMLExtractor`` reads one HTML file; ``BrainWriter`` appends the
resulting snapshot to a ``<value-stream>-history.json`` file. The ``rrr-ingest`` CLI wires
both together.
"""

from rrr.ingest.brain_writer import BrainWriter
from rrr.ingest.html_extractor import HTMLExtractor

__all__ = ["HTMLExtractor", "BrainWriter"]
