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

print("=" * 100)
print("COMPREHENSIVE JSON STRUCTURE EXPORT")
print("=" * 100)

print(f"\nFile: C:\Study\RRR\input\RKT Program Metrics Report.html")
print(f"Line: 270 (const __REPORT__ = {{...}};)")
print(f"JSON Size: {len(json_str):,} characters")
print(f"Total Releases: {len(releases)}")

print("\n" + "=" * 100)
print("PART 1: TOP-LEVEL __REPORT__ STRUCTURE")
print("=" * 100)

top_keys = list(data.keys())
print(f"\nTop-level keys: {top_keys}")

for key in top_keys:
    value = data[key]
    if key == 'generated':
        print(f"\n{key}: \"{value}\"")
    elif key == 'releases':
        print(f"\n{key}: array with {len(value)} release objects")
        print(f"  Each release has: {sorted(value[0].keys())}")
    elif key == 'program':
        print(f"\n{key}: dict with aggregate metrics")
        print(f"  Keys: {list(value.keys())}")
        for sub_key in value.keys():
            sub_val = value[sub_key]
            if isinstance(sub_val, dict):
                print(f"    {sub_key}: dict with keys {list(sub_val.keys())}")
    elif key == 'launch_pages':
        print(f"\n{key}: dict organizing releases by launch month")
        print(f"  Launch months: {list(value.keys())}")
        first_launch = list(value.values())[0]
        if first_launch:
            print(f"  Each launch contains metrics: {list(first_launch.keys())[:8]}...")

print("\n" + "=" * 100)
print("PART 2: INDIVIDUAL RELEASE FIELD TYPES AND SAMPLES")
print("=" * 100)

sample_release = releases[0]
print(f"\nSample release: '{sample_release['ir_name']}'")
print(f"Total fields: {len(sample_release)}\n")

# Categorize fields
metric_fields = {}
for field_name, field_value in sample_release.items():
    if isinstance(field_value, dict):
        sub_keys = list(field_value.keys())
        metric_type = "time-series" if 'labels' in sub_keys else "matrix-data"
        metric_fields[field_name] = {
            'type': metric_type,
            'sub_keys': sub_keys,
            'sample': field_value
        }
    elif field_value is None:
        metric_fields[field_name] = {'type': 'null', 'sample': None}
    elif isinstance(field_value, str):
        metric_fields[field_name] = {'type': 'string', 'sample': field_value}
    else:
        metric_fields[field_name] = {'type': type(field_value).__name__, 'sample': field_value}

for field_name in sorted(metric_fields.keys()):
    info = metric_fields[field_name]
    print(f"{field_name:<30} | Type: {info['type']:<15} | Sample: {str(info['sample'])[:60]}")

print("\n" + "=" * 100)
print("PART 3: PROGRAMME/PORTFOLIO EXTRACTION PATTERNS")
print("=" * 100)

print("\nProgramme codes FOUND IN ir_name strings (no separate field exists):\n")

programmes_found = {}
for release in releases:
    ir_name = release['ir_name']
    
    # Check each programme pattern
    if 'AIMS -' in ir_name or 'AIMS-' in ir_name:
        prog = 'AIMS'
    elif 'PIMS -' in ir_name or 'PIMS-' in ir_name:
        prog = 'PIMS'
    elif 'EIMS -' in ir_name or 'EIMS-' in ir_name:
        prog = 'EIMS'
    elif 'R5' in ir_name:
        prog = 'R5'
    elif 'R6' in ir_name:
        prog = 'R6'
    elif '(NEO)' in ir_name:
        prog = 'NEO'
    elif '(ME&Q)' in ir_name:
        prog = 'ME&Q'
    elif 'R@W' in ir_name:
        prog = 'R@W'
    elif 'OS&M' in ir_name or 'OSM' in ir_name:
        prog = 'OS&M'
    else:
        prog = 'NONE'
    
    if prog not in programmes_found:
        programmes_found[prog] = []
    programmes_found[prog].append(ir_name)

for prog in sorted(programmes_found.keys()):
    count = len(programmes_found[prog])
    print(f"{prog:<10} ({count:2d} releases):")
    for ir_name in programmes_found[prog][:3]:
        print(f"           - {ir_name}")
    if len(programmes_found[prog]) > 3:
        print(f"           ... and {len(programmes_found[prog])-3} more")

print("\n" + "=" * 100)
print("PART 4: DEPENDENCY REFERENCES IN ir_name")
print("=" * 100)

print("\nReleases with embedded dependency information:\n")

for release in releases:
    ir_name = release['ir_name']
    if 'Dependency' in ir_name:
        print(f"Release: {ir_name}")
        
        # Parse the dependency clause
        match = re.search(r'Dependency for:\s*([^;]+);\s*Launch:\s*(.+?)(?:\)|$)', ir_name)
        if match:
            print(f"  >> Is a dependency FOR programme/release: {match.group(1).strip()}")
            print(f"  >> Enables launch of: {match.group(2).strip()[:60]}...")
        print()

print("\n" + "=" * 100)
print("PART 5: LAUNCH_PAGES ORGANIZATION (Top-level Grouping)")
print("=" * 100)

launch_pages = data.get('launch_pages', {})

print(f"\nLaunch months identified: {sorted(launch_pages.keys())}\n")

for launch_month in sorted(launch_pages.keys()):
    metrics = launch_pages[launch_month]
    if metrics:
        print(f"{launch_month}:")
        print(f"  Aggregate metrics: {list(metrics.keys())[:8]}...")

print("\n\nNOTE: The 'launch_pages' object contains AGGREGATE metrics by month.")
print("Individual releases do NOT have a 'launch_month' or 'launch_date' field.")
print("The mapping of releases to launches must be inferred from ir_name matching.")

print("\n" + "=" * 100)
print("PART 6: SUMMARY TABLE")
print("=" * 100)

print(f"\nTotal releases in JSON: {len(releases)}")
print(f"\nFields present on every release: {len(releases[0])}")
print(f"\nField list: {sorted(releases[0].keys())}")

