import json
import re

# Read the HTML file
html_path = r"c:\Study\RRR\input\RKT Program Metrics Report.html"
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the JSON from the const __REPORT__ = {...};
match = re.search(r'const __REPORT__ = ({.*?});', content, re.DOTALL)
json_str = match.group(1)
data = json.loads(json_str)

releases = data.get('releases', [])

print("=" * 80)
print("DEPENDENCY AND REFERENCE ANALYSIS")
print("=" * 80)

print("\n[1] RELEASES MENTIONING DEPENDENCIES OR DEPENDENCIES")
print("-" * 80)

dependency_releases = []
for release in releases:
    ir_name = release.get('ir_name', '')
    if 'Dependency' in ir_name or 'dependency' in ir_name:
        dependency_releases.append(release)
        print(f"\nRelease: {ir_name}")
        
        # Try to parse dependency info
        dep_match = re.search(r'Dependency for:\s*([^;]+);?\s*Launch:\s*(.+?)(?:\)|$)', ir_name)
        if dep_match:
            dep_for = dep_match.group(1).strip()
            launch_for = dep_match.group(2).strip()
            print(f"  -> Dependency FOR: {dep_for}")
            print(f"  -> LAUNCHES: {launch_for}")

print("\n" + "=" * 80)
print("[2] PROGRAMME CODES AND THEIR RELEASES")
print("=" * 80)

programmes = {}
programme_patterns = {
    'AIMS': r'\bAIMS\b',
    'PIMS': r'\bPIMS\b',
    'EIMS': r'\bEIMS\b',
    'R5': r'\bR5\b',
    'R6': r'\bR6\b',
    'NEO': r'\(NEO\)',
    'ME&Q': r'\(ME&Q\)',
    'R@W': r'R@W',
    'OS&M': r'OS&M|OSM',
}

for prog_name, pattern in programme_patterns.items():
    programmes[prog_name] = []

for release in releases:
    ir_name = release.get('ir_name', '')
    for prog_name, pattern in programme_patterns.items():
        if re.search(pattern, ir_name):
            programmes[prog_name].append(ir_name)

for prog_name, release_list in sorted(programmes.items()):
    if release_list:
        print(f"\n{prog_name} ({len(release_list)} releases):")
        for ir_name in release_list:
            print(f"  - {ir_name}")

print("\n" + "=" * 80)
print("[3] CHECKING LAUNCH_PAGES ORGANIZATION")
print("=" * 80)

launch_pages = data.get('launch_pages', {})

print(f"\nLaunch pages structure:")
for launch_key in launch_pages.keys():
    launch_data = launch_pages[launch_key]
    
    # Count which releases are in this launch
    release_count = 0
    if isinstance(launch_data, dict):
        # The launch data has metrics, but we need to infer which releases are included
        # This is harder to determine from the metrics alone
        print(f"\n{launch_key}:")
        print(f"  Metrics: {list(launch_data.keys())[:5]}...")

# Try to infer releases by launch from ir_name patterns
print("\n\nInferred Release Groupings by Launch Date:")
print("-" * 80)

launch_keywords = {
    'June 2026': ['Before & After', 'Meeting Scheduler', 'First Time Access'],
    'July 2026': [],
    'September 2026': [],
    'October 2026': [],
    'November 2026': [],
}

print("\nNote: Releases don't have explicit 'launch_date' field.")
print("The 'launch_pages' top-level object groups METRICS by launch month,")
print("but individual releases don't reference which launch they belong to.")

print("\n" + "=" * 80)
print("[4] FINAL SUMMARY")
print("=" * 80)

print("""
KEY FINDINGS:

1. PROGRAMME/VALUE STREAM EXTRACTION:
   - Programme codes are EMBEDDED in the ir_name string
   - Common codes: AIMS, PIMS, EIMS, R5, R6, NEO, ME&Q, R@W, OS&M
   - Extraction strategies needed:
     * Pattern: "AIMS - " (code at start with dash)
     * Pattern: "(ME&Q)" (code in parentheses)
     * Pattern: "R@W" (code without markers)
   - Some releases have no programme code (generic/shared releases)

2. DEPENDENCY INFORMATION:
   - Only 2 releases mention dependencies in ir_name:
     * "Associate Desktop + CSCO IVR (Dependency for: DIST; Launch: Terminations Cash Withdrawals)"
     * "Onboarding Automation (Dependency for: OS&M; Launch: RetirePlus Pro Target Date...)"
   - NO separate dependency fields in individual releases
   - Dependency info is TEXT-ONLY in ir_name, not structured data

3. RELEASE FIELDS (20 fields total):
   Fields present on ALL releases:
   - Metrics: sp_closed, defects_closed, e2e_overall, e2e_progress, e2e_trend
   - Trending: weekly, monthly
   - Quality: defect_priority, defect_stage, defect_type, defect_age, defect_trend
   - Planning: feature_pivot, pv
   - Testing: uat_status, uat_execution, uat_execution_subrelease (often null)
   - Code Quality: sq_caps, sq_feats
   - Summary: summary (scalar metrics)

4. TOP-LEVEL ORGANIZATION:
   - "program": aggregate metrics across ALL releases
   - "launch_pages": metrics GROUPED BY LAUNCH MONTH
   - "releases": individual release objects
   - "generated": timestamp

5. WHAT'S MISSING:
   - No explicit "programme" or "value_stream" field on releases
   - No "parent_release", "dependent_releases", "linked_releases" fields
   - No launch_date on individual releases
   - No release_id or unique identifier beyond ir_name
   - No business_unit, work_type, or portfolio fields

6. DATA QUALITY:
   - All 41 releases have IDENTICAL field structure
   - Some releases have empty metrics (e.g., e2e_overall: null for some)
   - uat_status and uat_execution fields are often null
""")

