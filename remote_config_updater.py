import re, sys, json, argparse
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
import urllib.request

def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Update Firebase Remote Config conditions for iOS and Android apps',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--config', 
        help='Path or URL to config.json (optional). If not provided, updates both iOS and Android')
    parser.add_argument('--service-account', required=True,
        help='Path or URL to Firebase service account credentials JSON file')
    parser.add_argument('--version', required=True,
        help='New version number (e.g., 1.0.1)')
    parser.add_argument('--build', required=True, type=int,
        help='New build number (e.g., 1001)')
    return parser.parse_args()

def load_json(path_or_url):
    """Load JSON from local file or URL"""
    if path_or_url.startswith(('http://', 'https://')):
        with urllib.request.urlopen(path_or_url) as response:
            return json.loads(response.read().decode())
    else:
        with open(path_or_url) as f:
            return json.load(f)

# Parse command line arguments
args = parse_arguments()

# Load service account credentials and extract project ID
sa_info = load_json(args.service_account)
PROJECT_ID = sa_info['project_id']

# Determine targets based on config or default both OS
if args.config:
    cfg = load_json(args.config)
    TARGETS = cfg['targets']
    
    # Validate version/build with command line args
    for target in TARGETS:
        if target['new_version'] != args.version:
            raise ValueError(f"Config version {target['new_version']} doesn't match command line version {args.version}")
        if int(target['new_build']) != args.build:
            raise ValueError(f"Config build {target['new_build']} doesn't match command line build {args.build}")
else:
    # Default to both platforms with command line version/build
    TARGETS = [
        {
            'os': 'Android',
            'new_version': args.version,
            'new_build': args.build
        },
        {
            'os': 'iOS',
            'new_version': args.version,
            'new_build': args.build
        }
    ]

# Color sequence for conditions
COLOR_SEQUENCE = [
    'BLUE', 'BROWN', 'CYAN', 'DEEP_ORANGE', 'GREEN',
    'INDIGO', 'LIME', 'ORANGE', 'PINK', 'PURPLE', 'TEAL'
]

# --- Colour helpers ---

COLOR_TO_IDX = {c: i for i, c in enumerate(COLOR_SEQUENCE)}

def color_index(color: str) -> int:
    """Return the colour's index in COLOR_SEQUENCE or -1 if unknown."""
    return COLOR_TO_IDX.get(color, -1)

def next_color(prev_colors):
    """Given a list of previous colours, return the next colour in sequence."""
    highest_idx = max((color_index(c) for c in prev_colors if c), default=-1)
    return COLOR_SEQUENCE[(highest_idx + 1) % len(COLOR_SEQUENCE)]

def last_color_for_target(template, latest_map, target):
    """Return the tagColor of the latest condition for the given target OS."""
    os_key = target['os']
    prev_build = latest_map[os_key]['build']
    for cond in template.get('conditions', []):
        if (
            f"app.build.==(['{prev_build}'])" in cond.get('expression', '')
            and COND_REGEX.match(cond['name'])
            and COND_REGEX.match(cond['name']).group('os') == os_key
        ):
            return cond.get('tagColor')
    return None

# Auth setup
creds = service_account.Credentials.from_service_account_file(
    'credentials/service_account.json',
    scopes=['https://www.googleapis.com/auth/firebase.remoteconfig']
)
session = AuthorizedSession(creds)

BASE_URL = f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT_ID}/remoteConfig"

# Regex to parse condition names
COND_REGEX = re.compile(
    r"v(?P<version>[\d\.]+)\s+Prod Env\s+-\s+"
    r"(?P<os>Android|iOS)\s+(?P<build>\d+)",
    re.IGNORECASE
)

def fetch_template():
    resp = session.get(BASE_URL)
    if resp.status_code != 200:
        raise RuntimeError(f"Fetch failed: {resp.text}")
    return resp.headers['ETag'], resp.json()

def push_template(template, etag):
    headers = {'If-Match': etag}
    resp = session.put(BASE_URL, headers=headers, json=template)
    if resp.status_code != 200:
        raise RuntimeError(f"Update failed: {resp.text}")
    print("✅ Remote Config updated")

def discover_latest(template):
    latest = {}
    for cond in template.get('conditions', []):
        m = COND_REGEX.match(cond['name'])
        if not m:
            continue
        os_key  = m.group('os')
        ver     = m.group('version')
        build   = int(m.group('build'))
        if os_key not in latest:
            latest[os_key] = {'version': ver, 'build': build}
        else:
            # compare versions
            lv = latest[os_key]['version']
            if tuple(map(int, ver.split('.'))) > tuple(map(int, lv.split('.'))):
                latest[os_key]['version'] = ver
            # compare builds
            if build > latest[os_key]['build']:
                latest[os_key]['build'] = build
    return latest

def get_next_color(current_color):
    if not current_color:
        return COLOR_SEQUENCE[0]
    try:
        current_index = COLOR_SEQUENCE.index(current_color)
        next_index = (current_index + 1) % len(COLOR_SEQUENCE)
        return COLOR_SEQUENCE[next_index]
    except ValueError:
        return COLOR_SEQUENCE[0]

def clone_for_target(template, latest_map, target, new_color):
    os_key       = target['os']
    new_ver      = target['new_version']
    new_build    = int(target['new_build'])
    prev_ver     = target.get('previous_version') or latest_map[os_key]['version']
    prev_build   = latest_map[os_key]['build']

    # validations
    if new_build <= prev_build:
        raise ValueError(f"{os_key}: new_build ({new_build}) ≤ latest ({prev_build})")
    if tuple(map(int, new_ver.split('.'))) < tuple(map(int, latest_map[os_key]['version'].split('.'))):
        raise ValueError(f"{os_key}: new_version ({new_ver}) < latest ({latest_map[os_key]['version']})")

    # find matching conditions
    matches = [
       c for c in template['conditions']
       if f"app.build.==(['{prev_build}'])" in c.get('expression','')
       and COND_REGEX.match(c['name']) is not None
       and COND_REGEX.match(c['name']).group('os') == os_key
    ]

    new_conds = []
    for cond in matches:
        new_name = re.sub(
            rf"v{re.escape(prev_ver)} Prod Env - {os_key} {prev_build}",
            f"v{new_ver} Prod Env - {os_key} {new_build}",
            cond['name']
        )
        new_expr = cond['expression']\
            .replace(f"app.build.==(['{prev_build}'])", f"app.build.==(['{new_build}'])")
        copy = {**cond, 'name': new_name, 'expression': new_expr, 'tagColor': new_color}
        new_conds.append(copy)

    # show preview
    print(f"\n{os_key} will get {len(new_conds)} new condition(s):")
    for c in new_conds:
        print("  -", c['name'])

    # map parameter updates
    param_map = []
    for key,param in template.get('parameters', {}).items():
        cvs = param.get('conditionalValues', {})
        for old in [c['name'] for c in matches]:
            if old in cvs:
                new = old.replace(prev_ver,f"{new_ver}").replace(str(prev_build),str(new_build))
                param_map.append((key, old, new))

    # Get unique parameter count
    affected_params = len(set(p for p,_,_ in param_map))
    print(f"\nParameter mappings ({affected_params} parameters):")
    for p,old,new in param_map:
        print(f"  • {p}: {old} → {new}")

    return new_conds, param_map

def main():
    etag, tpl = fetch_template()
    latest = discover_latest(tpl)

    # uniform next colour for this run
    prev_colors = [last_color_for_target(tpl, latest, tgt) for tgt in TARGETS]
    uniform_color = next_color(prev_colors)

    all_new_conds = []
    all_param_maps = []
    for tgt in TARGETS:
        new_conds, param_maps = clone_for_target(tpl, latest, tgt, uniform_color)
        tpl['conditions'].extend(new_conds)
        for key, old, new in param_maps:
            val = tpl['parameters'][key]['conditionalValues'][old]
            tpl['parameters'][key]['conditionalValues'][new] = val
        all_new_conds += new_conds
        all_param_maps += param_maps

    # final confirmation
    ans = input("\nProceed with these changes? [y/N]: ").strip().lower()
    if ans != 'y':
        sys.exit("✋ Aborted")

    push_template(tpl, etag)

if __name__ == "__main__":
    main()
