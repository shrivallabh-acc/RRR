"""Tests for the HTML ingest layer (ADR-0018): HTMLExtractor, BrainWriter, and rrr-ingest CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rrr.ingest.brain_writer import BrainWriter
from rrr.ingest.cli import ingest
from rrr.ingest.html_extractor import (
    HTMLExtractor,
    _defect_trend_last5,
    _defects_open,
    _e2e_latest,
    _extract_programme,
    _extract_relationship,
    _map_release,
    _normalize_name,
    _parse_generated,
    _parse_toc,
    _pv_latest,
    _sq_avg,
    _sq_below_1,
    _summary,
    _weekly_last3,
)

# ---------------------------------------------------------------------------
# Fixtures — minimal synthetic __REPORT__ data (not the full 2.3 MB HTML)
# ---------------------------------------------------------------------------

_MINIMAL_RELEASE: dict = {
    "ir_name": "Launch 99 - Test",
    "summary": {
        "committed_sp": 100,
        "uncommitted_sp": 0,
        "total": 100,
        "closed": 90,
        "remaining": 10,
        "pct_committed": 90,
        "pct_total": 90,
        "pct": 90,
    },
    "weekly": {
        "labels": ["2026-05-11", "2026-05-18", "2026-05-25", "2026-06-01", "2026-06-08"],
        "values": [10, 8, 5, 3, 2],
    },
    "pv": {
        "labels": ["2026-01-01", "2026-06-01"],
        "pv": [0, 100],
        "actual": [0, 90],
        "total_sp": [100, 100],
    },
    "sq_caps": {"names": ["repo-a", "repo-b", "repo-c"], "scores": [0.9, 0.2, 0.0]},
    "defect_trend": {
        "labels": [
            "2026-06-01",
            "2026-06-08",
            "2026-06-09",
            "2026-06-10",
            "2026-06-11",
            "2026-06-12",
        ],
        "created": [2, 1, 3, 0, 1, 2],
        "resolved": [0, 2, 1, 1, 0, 3],
    },
    "defect_priority": {
        "labels": ["Critical", "Minor", "Unassigned"],
        "statuses": ["In Dev", "In Test"],
        "matrix": {"In Dev": [2, 1, 0], "In Test": [1, 0, 1]},
    },
    "defects_closed": {"labels": ["2026-06-01", "2026-06-08"], "values": [3, 5]},
    "e2e_overall": {
        "labels": ["2026-06-01", "2026-06-08"],
        "passed": [50.0, 62.0],
        "failed": [5.0, 3.0],
        "planned": [70.0, 70.0],
    },
}

_REPORT_JSON = json.dumps(
    {
        "generated": "June 22, 2026 09:00 AM EST",
        "releases": [_MINIMAL_RELEASE],
        "program": {},
        "launch_pages": {},
    }
)
_MINIMAL_HTML = f"<html><script>\nconst __REPORT__ = {_REPORT_JSON};\n</script></html>"


# ---------------------------------------------------------------------------
# _parse_generated
# ---------------------------------------------------------------------------


def test_parse_generated_extracts_iso_date() -> None:
    assert _parse_generated("June 19, 2026 05:57 AM EST") == "2026-06-19"


def test_parse_generated_handles_single_digit_day() -> None:
    assert _parse_generated("June 1, 2026 10:00 AM EST") == "2026-06-01"


# ---------------------------------------------------------------------------
# Individual mapping helpers
# ---------------------------------------------------------------------------


def test_summary_extracts_four_fields() -> None:
    result = _summary(_MINIMAL_RELEASE["summary"])
    assert result == {"total": 100, "closed": 90, "remaining": 10, "pct": 90}


def test_weekly_last3_returns_last_three() -> None:
    result = _weekly_last3(_MINIMAL_RELEASE["weekly"])
    assert len(result) == 3
    assert result[-1] == {"week": "2026-06-08", "value": 2}


def test_weekly_last3_fewer_than_three() -> None:
    result = _weekly_last3({"labels": ["2026-06-01"], "values": [5]})
    assert result == [{"week": "2026-06-01", "value": 5}]


def test_pv_latest_takes_last_element() -> None:
    result = _pv_latest(_MINIMAL_RELEASE["pv"])
    assert result == {"planned": 100, "actual": 90}


def test_pv_latest_empty_returns_zeros() -> None:
    assert _pv_latest({}) == {"planned": 0, "actual": 0}


def test_pv_latest_skips_trailing_nulls() -> None:
    # Real RKT HTML extends series to planned end date — future entries are null.
    result = _pv_latest({"pv": [0, 50, 100, None, None], "actual": [0, 40, None, None, None]})
    assert result == {"planned": 100, "actual": 40}


def test_weekly_last3_skips_null_values() -> None:
    result = _weekly_last3(
        {"labels": ["2026-06-01", "2026-06-08", "2026-06-15"], "values": [5, None, 3]}
    )
    assert len(result) == 2
    assert result[-1] == {"week": "2026-06-15", "value": 3}


def test_sq_avg_ignores_null_scores() -> None:
    assert _sq_avg({"scores": [None, None]}) == 0.0
    result = _sq_avg({"scores": [1.0, None, 0.0]})
    assert abs(result - round(0.5 * 1.5, 4)) < 1e-6


def test_defect_trend_treats_null_as_zero() -> None:
    result = _defect_trend_last5(
        {"created": [2, None, 1], "resolved": [0, None, 1], "labels": ["a", "b", "c"]}
    )
    assert result == [2, 2, 2]


def test_e2e_latest_skips_trailing_nulls() -> None:
    result = _e2e_latest(
        {"passed": [50.0, 62.0, None], "failed": [5.0, 3.0, None], "planned": [70.0, 70.0, None]}
    )
    assert result == {"passed": 62, "failed": 3, "planned": 70}


def test_sq_avg_converts_0_to_2_scale_to_0_to_3() -> None:
    # scores [0.9, 0.2, 0.0] → mean = 0.3667 → × 1.5 = 0.55 (HTML 0-2 → brain 0-3)
    result = _sq_avg(_MINIMAL_RELEASE["sq_caps"])
    assert abs(result - round((0.9 + 0.2 + 0.0) / 3 * 1.5, 4)) < 1e-6


def test_sq_avg_clamps_at_3() -> None:
    # scores above 2.0 are exceptional; result must not exceed 3.0
    result = _sq_avg({"scores": [2.2, 2.1, 2.0]})
    assert result <= 3.0


def test_sq_avg_empty_returns_zero() -> None:
    assert _sq_avg({}) == 0.0


def test_sq_below_1_flags_low_scoring_repos() -> None:
    # threshold = 2/3 on HTML 0-2 scale (= 1.0 on brain 0-3 scale)
    # repo-b: 0.2 < 2/3 → flagged; repo-c: 0.0 < 2/3 → flagged; repo-a: 0.9 >= 2/3 → ok
    result = _sq_below_1(_MINIMAL_RELEASE["sq_caps"])
    assert "repo-b" in result
    assert "repo-c" in result
    assert "repo-a" not in result


def test_defect_trend_last5_computes_running_open() -> None:
    # created = [2,1,3,0,1,2], resolved = [0,2,1,1,0,3]
    # running: 2, 1, 3, 2, 3, 2  → last 5 = [1,3,2,3,2]
    result = _defect_trend_last5(_MINIMAL_RELEASE["defect_trend"])
    assert result == [1, 3, 2, 3, 2]


def test_defect_trend_never_goes_negative() -> None:
    # If more resolved than created, open count stays at 0
    result = _defect_trend_last5({"created": [1], "resolved": [5], "labels": ["2026-06-01"]})
    assert result == [0]


def test_defects_open_sums_matrix_by_priority() -> None:
    result = _defects_open(_MINIMAL_RELEASE["defect_priority"])
    # Critical: In Dev=2, In Test=1 → 3
    assert result["by_severity"]["critical"] == 3
    # Minor: In Dev=1, In Test=0 → 1
    assert result["by_severity"]["minor"] == 1
    # Total: 3 + 1 + 1(Unassigned) = 5
    assert result["total"] == 5


def test_e2e_latest_takes_last_entry() -> None:
    result = _e2e_latest(_MINIMAL_RELEASE["e2e_overall"])
    assert result == {"passed": 62, "failed": 3, "planned": 70}


def test_e2e_latest_returns_none_when_empty() -> None:
    assert _e2e_latest({}) is None
    assert _e2e_latest({"passed": [], "failed": [], "planned": []}) is None


# ---------------------------------------------------------------------------
# Full _map_release
# ---------------------------------------------------------------------------


def test_map_release_produces_all_brain_fields() -> None:
    result = _map_release(_MINIMAL_RELEASE)
    assert result["ir_name"] == "Launch 99 - Test"
    assert result["summary"]["total"] == 100
    assert result["pv_latest"] == {"planned": 100, "actual": 90}
    assert result["e2e_latest"] == {"passed": 62, "failed": 3, "planned": 70}
    assert result["defects_closed_cumulative"] == 8  # 3 + 5
    assert result["programme"] == "OSM"  # no prefix → native OSM


# ---------------------------------------------------------------------------
# _extract_programme
# ---------------------------------------------------------------------------


def test_extract_programme_aims_prefix() -> None:
    assert _extract_programme("AIMS - MMO Fund to Fund") == "AIMS"


def test_extract_programme_pims_prefix() -> None:
    assert _extract_programme("PIMS - Terminations Cash Withdrawals") == "PIMS"


def test_extract_programme_eims_prefix() -> None:
    assert _extract_programme("EIMS - AM F2F, AM RCRCP") == "EIMS"


def test_extract_programme_r5_prefix() -> None:
    assert _extract_programme("R5 IS - DT Terminations Cash Withdrawal") == "R5"


def test_extract_programme_r6_prefix() -> None:
    assert _extract_programme("R6 PIMS - RetirePlus Pro") == "R6"


def test_extract_programme_meq_suffix() -> None:
    assert _extract_programme("Meeting Scheduler (Full) (ME&Q)") == "ME&Q"


def test_extract_programme_neo_suffix() -> None:
    assert _extract_programme("First Time Access (NEO)") == "NEO"


def test_extract_programme_raw_embedded() -> None:
    assert _extract_programme("First Time Access with Self Enrollment; R@W") == "R@W"


def test_extract_programme_no_code_returns_osm() -> None:
    # Native OSM releases carry no programme prefix or suffix.
    assert _extract_programme("RetirePlus RC/RCP Enrollment") == "OSM"
    assert _extract_programme("Fund to Fund Transfers") == "OSM"
    assert _extract_programme("Before & After (Accum)") == "OSM"


def test_extract_programme_case_insensitive() -> None:
    assert _extract_programme("aims - lowercase test") == "AIMS"


# ---------------------------------------------------------------------------
# _extract_relationship
# ---------------------------------------------------------------------------


def test_extract_relationship_returns_none_for_normal_release() -> None:
    assert _extract_relationship("RetirePlus RC/RCP Enrollment") is None
    assert _extract_relationship("Fund to Fund Transfers") is None


def test_extract_relationship_parses_simple_dependency() -> None:
    ir = (
        "Associate Desktop + CSCO IVR (Dependency for: DIST; Launch: Terminations Cash Withdrawals)"
    )
    result = _extract_relationship(ir)
    assert result is not None
    assert result["dependency_for"] == "DIST"
    assert result["enables_release"] == "Terminations Cash Withdrawals"


def test_extract_relationship_handles_nested_parens_in_launch_name() -> None:
    # The downstream release name may itself contain parentheses.
    ir = (
        "Onboarding Automation "
        "(Dependency for: OS&M; Launch: RetirePlus Pro (Adopt & Manage) DCI & Partial STP)"
    )
    result = _extract_relationship(ir)
    assert result is not None
    assert result["dependency_for"] == "OS&M"
    assert result["enables_release"] == "RetirePlus Pro (Adopt & Manage) DCI & Partial STP"


def test_extract_relationship_case_insensitive() -> None:
    ir = "Some Release (dependency for: DIST; launch: Target Release)"
    result = _extract_relationship(ir)
    assert result is not None
    assert result["dependency_for"] == "DIST"


# ---------------------------------------------------------------------------
# HTMLExtractor
# ---------------------------------------------------------------------------


def test_html_extractor_parses_minimal_html(tmp_path: Path) -> None:
    html_file = tmp_path / "report.html"
    html_file.write_text(_MINIMAL_HTML, encoding="utf-8")

    date, releases = HTMLExtractor().extract(html_file)
    assert date == "2026-06-22"
    assert len(releases) == 1
    assert releases[0]["ir_name"] == "Launch 99 - Test"


def test_html_extractor_raises_on_missing_report(tmp_path: Path) -> None:
    bad = tmp_path / "bad.html"
    bad.write_text("<html>no report here</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="__REPORT__"):
        HTMLExtractor().extract(bad)


# ---------------------------------------------------------------------------
# BrainWriter
# ---------------------------------------------------------------------------


def test_brain_writer_creates_new_file(tmp_path: Path) -> None:
    writer = BrainWriter()
    path = writer.append_snapshot(tmp_path, "Retirement-Services", "2026-06-22", [{"ir_name": "X"}])
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["value_stream"] == "Retirement-Services"
    assert len(data["snapshots"]) == 1
    assert data["snapshots"][0]["date"] == "2026-06-22"


def test_brain_writer_appends_second_snapshot(tmp_path: Path) -> None:
    writer = BrainWriter()
    writer.append_snapshot(tmp_path, "RS", "2026-06-15", [{"ir_name": "A"}])
    writer.append_snapshot(tmp_path, "RS", "2026-06-22", [{"ir_name": "B"}])
    data = json.loads((tmp_path / "RS-history.json").read_text())
    assert len(data["snapshots"]) == 2
    # Snapshots should be chronological.
    assert data["snapshots"][0]["date"] == "2026-06-15"
    assert data["snapshots"][1]["date"] == "2026-06-22"


def test_brain_writer_upsert_replaces_same_date(tmp_path: Path) -> None:
    writer = BrainWriter()
    writer.append_snapshot(tmp_path, "RS", "2026-06-22", [{"ir_name": "old"}])
    writer.append_snapshot(tmp_path, "RS", "2026-06-22", [{"ir_name": "new"}])
    data = json.loads((tmp_path / "RS-history.json").read_text())
    assert len(data["snapshots"]) == 1
    assert data["snapshots"][0]["releases"][0]["ir_name"] == "new"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_ingest_processes_html_file(tmp_path: Path) -> None:
    html_file = tmp_path / "report.html"
    html_file.write_text(_MINIMAL_HTML, encoding="utf-8")
    brain_dir = tmp_path / "brain"

    result = CliRunner().invoke(
        ingest,
        ["--html-dir", str(tmp_path), "--brain-dir", str(brain_dir), "--value-stream", "Test-VS"],
    )
    assert result.exit_code == 0, result.output
    out_file = brain_dir / "Test-VS-history.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["snapshots"][0]["date"] == "2026-06-22"


def test_cli_ingest_fails_on_empty_html_dir(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        ingest,
        [
            "--html-dir",
            str(tmp_path),
            "--brain-dir",
            str(tmp_path / "brain"),
            "--value-stream",
            "VS",
        ],
    )
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# _normalize_name
# ---------------------------------------------------------------------------


def test_normalize_name_unescapes_html_entities() -> None:
    assert _normalize_name("Before &amp; After (Accum)") == "Before & After (Accum)"


def test_normalize_name_collapses_whitespace() -> None:
    assert _normalize_name("  Fund  to  Fund  ") == "Fund to Fund"


def test_normalize_name_handles_plain_ampersand_unchanged() -> None:
    # ir_names from __REPORT__ already have plain & — should be unchanged.
    assert _normalize_name("Before & After (Accum)") == "Before & After (Accum)"


# ---------------------------------------------------------------------------
# _parse_toc
# ---------------------------------------------------------------------------

# Minimal HTML stub that has a TOC slide followed by the next page.
_TOC_HTML = """\
<div class="page" data-ribbon="Table of Contents">
  <span class="toc-vs-label">Education &amp; Advice</span>
  <ul class="toc-releases">
    <li><a href="#rel0">Before &amp; After (Accum)</a></li>
    <li><a href="#rel1">Meeting Scheduler (Full) (ME&amp;Q)</a></li>
  </ul>
  <span class="toc-vs-label">Account Management</span>
  <ul class="toc-releases">
    <li><a href="#rel2">Fund to Fund</a></li>
  </ul>
</div>
<div class="page" data-ribbon="Other Slide">
"""


def test_parse_toc_extracts_vs_mapping() -> None:
    toc = _parse_toc(_TOC_HTML)
    assert toc["Before & After (Accum)"] == "Education & Advice"
    assert toc["Meeting Scheduler (Full) (ME&Q)"] == "Education & Advice"
    assert toc["Fund to Fund"] == "Account Management"


def test_parse_toc_normalizes_html_entities_in_vs_names() -> None:
    toc = _parse_toc(_TOC_HTML)
    # VS label "Education &amp; Advice" → "Education & Advice"
    assert "Education & Advice" in toc.values()


def test_parse_toc_returns_empty_when_no_toc_slide() -> None:
    toc = _parse_toc("<html><body>No TOC here</body></html>")
    assert toc == {}


def test_parse_toc_returns_empty_for_plain_report_html(_minimal_html_no_toc: str) -> None:
    # The minimal __REPORT__ HTML used in other tests has no TOC slide.
    toc = _parse_toc(_minimal_html_no_toc)
    assert toc == {}


# Expose _MINIMAL_HTML as a named fixture for re-use.
@pytest.fixture()
def _minimal_html_no_toc() -> str:
    return _MINIMAL_HTML


# ---------------------------------------------------------------------------
# _map_release with toc_vs_map
# ---------------------------------------------------------------------------


def test_map_release_includes_toc_value_stream_when_found() -> None:
    toc_map = {"Launch 99 - Test": "Account Management"}
    result = _map_release(_MINIMAL_RELEASE, toc_vs_map=toc_map)
    assert result["toc_value_stream"] == "Account Management"


def test_map_release_toc_value_stream_is_none_when_not_in_map() -> None:
    result = _map_release(_MINIMAL_RELEASE, toc_vs_map={"Other Release": "Some VS"})
    assert result["toc_value_stream"] is None


def test_map_release_toc_value_stream_is_none_when_map_empty() -> None:
    result = _map_release(_MINIMAL_RELEASE, toc_vs_map={})
    assert result["toc_value_stream"] is None


def test_map_release_toc_value_stream_is_none_when_no_map() -> None:
    result = _map_release(_MINIMAL_RELEASE)
    assert result["toc_value_stream"] is None


# ---------------------------------------------------------------------------
# End-to-end: HTMLExtractor populates toc_value_stream
# ---------------------------------------------------------------------------

_REPORT_WITH_TOC = (
    '<div class="page" data-ribbon="Table of Contents">\n'
    '  <span class="toc-vs-label">Account Management</span>\n'
    '  <ul class="toc-releases">\n'
    '    <li><a href="#rel0">Launch 99 - Test</a></li>\n'
    "  </ul>\n"
    "</div>\n"
    '<div class="page">\n'
    f"<html><script>\nconst __REPORT__ = {_REPORT_JSON};\n</script></html>"
)


def test_extractor_populates_toc_value_stream_from_toc(tmp_path: Path) -> None:
    html_file = tmp_path / "report.html"
    html_file.write_text(_REPORT_WITH_TOC, encoding="utf-8")
    _, releases = HTMLExtractor().extract(html_file)
    assert releases[0]["toc_value_stream"] == "Account Management"


def test_extractor_toc_value_stream_none_when_no_toc(tmp_path: Path) -> None:
    html_file = tmp_path / "report.html"
    html_file.write_text(_MINIMAL_HTML, encoding="utf-8")
    _, releases = HTMLExtractor().extract(html_file)
    assert releases[0]["toc_value_stream"] is None
