from remote_config_updater import fetch_template, COND_REGEX

# Fetch the current remote config template
etag, template = fetch_template()

# Print all conditions to debug
print("All conditions:")
for i, cond in enumerate(template.get('conditions', [])):
    print(f"\n{i+1}. Name: {cond['name']}")
    print(f"   Expression: {cond['expression']}")
    match = COND_REGEX.match(cond['name'])
    if match:
        print(f"   ✓ Matched regex: {match.groupdict()}")
    else:
        print(f"   ✗ Didn't match regex")

# Check expression patterns
print("\nExpression patterns for each OS:")
for os_key in ["Android", "iOS"]:
    patterns = set()
    for cond in template.get('conditions', []):
        if f"device.os == '{os_key.upper()}'" in cond.get('expression', ''):
            patterns.add(cond.get('expression', ''))
        elif f"device.os == '{os_key}'" in cond.get('expression', ''):
            patterns.add(cond.get('expression', ''))
    
    print(f"\n{os_key} expressions found: {len(patterns)}")
    for p in patterns:
        print(f"  - {p}") 