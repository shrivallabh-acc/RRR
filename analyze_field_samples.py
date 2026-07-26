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
print("SAMPLE DATA FROM KEY RELEASE FIELDS")
print("=" * 80)

# Print full details for first 3 releases
for i, release in enumerate(releases[:3]):
    print(f"\n\n{'=' * 80}")
    print(f"RELEASE {i+1}: {release.get('ir_name', 'N/A')}")
    print(f"{'=' * 80}")
    
    for field_name in sorted(release.keys()):
        field_value = release[field_name]
        
        print(f"\n{field_name}:")
        
        if isinstance(field_value, dict):
            # For dicts, show the structure
            if 'labels' in field_value:
                labels = field_value['labels']
                print(f"  (dict) labels: {labels[:3] if isinstance(labels, list) else labels}{'...' if isinstance(labels, list) and len(labels) > 3 else ''}")
            
            sub_keys = [k for k in field_value.keys() if k != 'labels']
            for sub_key in sub_keys[:3]:
                sub_val = field_value[sub_key]
                if isinstance(sub_val, list):
                    print(f"  {sub_key}: {sub_val[:2] if len(sub_val) > 2 else sub_val}{'...' if len(sub_val) > 2 else ''}")
                elif isinstance(sub_val, dict):
                    print(f"  {sub_key}: dict with {len(sub_val)} items")
                else:
                    print(f"  {sub_key}: {repr(sub_val)[:80]}")
        
        elif field_value is None:
            print(f"  (null)")
        
        elif isinstance(field_value, str):
            print(f"  (string) {repr(field_value)[:100]}")
        
        elif isinstance(field_value, (int, float, bool)):
            print(f"  (scalar) {field_value}")
        
        else:
            print(f"  ({type(field_value).__name__}) {repr(field_value)[:100]}")

print("\n\n" + "=" * 80)
print("COMPLETE ir_name VALUES FOR EXTRACTION TESTING")
print("=" * 80)
print("\nAll ir_name values (for programme extraction regex testing):\n")

for i, release in enumerate(releases, 1):
    ir_name = release.get('ir_name', '')
    # Try to extract programme code
    import re as regex_module
    # Look for patterns like (ACRONYM) or ACRONYM -
    programme_pattern = regex_module.search(r'([A-Z]+(?:&[A-Z]+)?)\s*[-:]|\(([A-Z]+(?:&[A-Z]+)?)\)', ir_name)
    programme = programme_pattern.group(1) or programme_pattern.group(2) if programme_pattern else "NOT FOUND"
    
    print(f"{i:2d}. {ir_name:<70} | Programme: {programme}")

