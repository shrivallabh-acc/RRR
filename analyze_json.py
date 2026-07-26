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
print(f"[INFO] Extracted JSON string length: {len(json_str)} chars\n")

# Parse JSON
try:
    data = json.loads(json_str)
except json.JSONDecodeError as e:
    print(f"ERROR: JSON parsing failed: {e}")
    exit(1)

print("=" * 80)
print("SECTION 1: TOP-LEVEL KEYS IN __REPORT__")
print("=" * 80)
top_level_keys = list(data.keys())
print(f"\nTop-level keys: {top_level_keys}\n")

# Show sample content for non-releases keys
for key in top_level_keys:
    if key != 'releases':
        value = data[key]
        if isinstance(value, (dict, list)):
            if isinstance(value, dict):
                sub_keys = list(value.keys())[:10]
                print(f"  {key}: dict with keys: {sub_keys}")
            else:
                print(f"  {key}: list with {len(value)} items")
                if value and isinstance(value[0], dict):
                    print(f"         first item keys: {list(value[0].keys())}")
        else:
            print(f"  {key}: {repr(value)[:100]}")

print("\n" + "=" * 80)
print("SECTION 2: RELEASES ARRAY - FIRST 3 RELEASES")
print("=" * 80)

releases = data.get('releases', [])
print(f"\nTotal releases: {len(releases)}\n")

for i, release in enumerate(releases[:3]):
    print(f"\n--- RELEASE {i+1} ---")
    print(f"ir_name: {release.get('ir_name', 'N/A')}")
    print(f"ALL KEYS in this release: {sorted(release.keys())}")
    
    # Look for programme/value stream related fields
    for key in release.keys():
        if any(term in key.lower() for term in ['program', 'value_stream', 'portfolio', 'business', 'work_type', 'group', 'category', 'area']):
            print(f"  ** {key}: {repr(release[key])[:150]}")
    
    # Look for dependency-related fields
    for key in release.keys():
        if any(term in key.lower() for term in ['depend', 'predecessor', 'successor', 'linked', 'related']):
            print(f"  ** {key}: {repr(release[key])[:150]}")

print("\n" + "=" * 80)
print("SECTION 3: CHECKING ir_name PATTERNS")
print("=" * 80)

print("\nFirst 5 release ir_name values:\n")
for i, release in enumerate(releases[:5]):
    ir_name = release.get('ir_name', 'N/A')
    print(f"  {i+1}. {ir_name}")

print("\n" + "=" * 80)
print("SECTION 4: LOOKING FOR RELEASE DEPENDENCY FIELDS")
print("=" * 80)

# Check all releases for dependency-related fields
dependency_fields = set()
for release in releases:
    for key in release.keys():
        if any(term in key.lower() for term in ['depend', 'predecessor', 'successor', 'linked', 'related', 'ref', 'id']):
            dependency_fields.add(key)

if dependency_fields:
    print(f"\nFields that might relate to dependencies: {sorted(dependency_fields)}\n")
    # Show samples
    for field in sorted(dependency_fields):
        sample_values = []
        for release in releases[:3]:
            if field in release:
                val = release[field]
                if val is not None:
                    sample_values.append(val)
        if sample_values:
            print(f"  {field}: {sample_values[:2]}")
else:
    print("\nNo dependency-related fields found in first 3 releases")

print("\n" + "=" * 80)
print("SECTION 5: EXHAUSTIVE FIELD LISTING (First Release)")
print("=" * 80)

if releases:
    first_release = releases[0]
    print(f"\nAll fields in first release ({first_release.get('ir_name', 'N/A')}):\n")
    for key, value in first_release.items():
        if isinstance(value, (dict, list)):
            if isinstance(value, dict):
                print(f"  {key}: dict with keys: {list(value.keys())}")
            else:
                print(f"  {key}: list with {len(value)} items")
        else:
            val_repr = repr(value)[:100]
            print(f"  {key}: {val_repr}")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
