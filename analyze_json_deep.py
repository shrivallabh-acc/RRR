import json
import re
from pathlib import Path

# Read the HTML file
html_path = r"c:\Study\RRR\input\RKT Program Metrics Report.html"
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the JSON from the const __REPORT__ = {...};
match = re.search(r'const __REPORT__ = ({.*?});', content, re.DOTALL)
if not match:
    print("ERROR: Could not find __REPORT__ JSON")
    exit(1)

json_str = match.group(1)
data = json.loads(json_str)

print("=" * 80)
print("DEEP ANALYSIS: PROGRAMME/VALUE STREAM INFORMATION")
print("=" * 80)

releases = data.get('releases', [])

# Pattern analysis for ir_name
print("\n[1] ANALYZING ir_name PATTERNS (looking for embedded programme info)\n")
print("All 41 releases and their ir_name values:")
print("-" * 80)

# Try to identify patterns
programme_keywords = ['AIMS', 'OSM', 'PIMS', 'DIST', 'R5', 'NEO', 'ME&Q', 'R@W']

for i, release in enumerate(releases):
    ir_name = release.get('ir_name', 'N/A')
    # Check if programme keyword is in ir_name
    found_keywords = [kw for kw in programme_keywords if kw in ir_name]
    keyword_str = f" [FOUND: {', '.join(found_keywords)}]" if found_keywords else ""
    print(f"{i+1:2d}. {ir_name}{keyword_str}")

print("\n" + "=" * 80)
print("[2] TOP-LEVEL STRUCTURE: 'program' key")
print("=" * 80)

program_data = data.get('program', {})
print(f"\nKeys in 'program': {list(program_data.keys())}")
for key in program_data.keys():
    val = program_data[key]
    if isinstance(val, dict):
        print(f"  {key}: dict with structure {list(val.keys())[:5]}...")
    elif isinstance(val, list):
        print(f"  {key}: list with {len(val)} items")
    else:
        print(f"  {key}: {type(val).__name__}")

print("\n" + "=" * 80)
print("[3] TOP-LEVEL STRUCTURE: 'launch_pages' key")
print("=" * 80)

launch_pages = data.get('launch_pages', {})
print(f"\nKeys in 'launch_pages': {list(launch_pages.keys())}")

for launch_key in launch_pages.keys():
    launch_data = launch_pages[launch_key]
    print(f"\n  {launch_key}:")
    if isinstance(launch_data, dict):
        for sub_key, sub_val in launch_data.items():
            if isinstance(sub_val, list):
                print(f"    {sub_key}: list with {len(sub_val)} items")
                if sub_val:
                    if isinstance(sub_val[0], dict):
                        print(f"             first item keys: {list(sub_val[0].keys())}")
                    else:
                        print(f"             first item: {repr(sub_val[0])[:80]}")
            elif isinstance(sub_val, dict):
                print(f"    {sub_key}: dict with keys: {list(sub_val.keys())}")
            else:
                print(f"    {sub_key}: {repr(sub_val)[:100]}")

print("\n" + "=" * 80)
print("[4] CHECKING IF THERE ARE SEPARATE PROGRAMME/PORTFOLIO FIELDS")
print("=" * 80)

# Check all unique keys across all releases
all_keys = set()
for release in releases:
    all_keys.update(release.keys())

print(f"\nAll unique keys across all {len(releases)} releases:")
print(f"{sorted(all_keys)}")

# Look for any release that might have additional fields
print("\n\nChecking for variations in release structure:")
key_counts = {}
for release in releases:
    key_tuple = tuple(sorted(release.keys()))
    if key_tuple not in key_counts:
        key_counts[key_tuple] = []
    key_counts[key_tuple].append(release.get('ir_name', 'N/A'))

if len(key_counts) == 1:
    print("All releases have identical field structure (good!)")
else:
    print(f"Found {len(key_counts)} different field structures:")
    for i, (keys, releases_with_keys) in enumerate(key_counts.items()):
        print(f"\n  Structure {i+1}: {sorted(keys)}")
        print(f"    Used by: {releases_with_keys}")

print("\n" + "=" * 80)
print("[5] CHECKING FOR DEPENDENCY REFERENCES IN ir_name")
print("=" * 80)

print("\nReleases with 'Dependency' or 'Launch:' in ir_name:\n")
for release in releases:
    ir_name = release.get('ir_name', '')
    if 'Dependency' in ir_name or 'Launch:' in ir_name or 'Dependent' in ir_name:
        print(f"  {ir_name}")

print("\n" + "=" * 80)
print("[6] SUMMARY")
print("=" * 80)

print(f"""
Total Releases: {len(releases)}

Top-level keys in __REPORT__: {list(data.keys())}

Release field names: {sorted(all_keys)}

Key Observations:
- All releases have identical field structure
- programme/portfolio info appears EMBEDDED in ir_name (e.g., "ME&Q", "R@W", "NEO")
- No separate programme/portfolio ID fields found in releases
- No dependency/linked_release fields in individual releases
- Dependency information MAY be embedded in ir_name strings (see "Dependency for:", "Launch:")
- The 'program' key at top level contains aggregate metrics across all releases
- The 'launch_pages' key organizes releases by launch date/month
""")

