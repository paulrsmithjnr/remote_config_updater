# Remote Config Updater

A Python utility to automate cloning Firebase Remote Config conditions across app versions and platforms (Android/iOS), previewing changes, and applying them via the REST API only after manual approval.

## Project Structure

```
remote_config_updater/
├── credentials/
│   └── service_account.json       # Firebase service account key
├── config.json                    # User inputs: per-OS version & build settings
├── remote_config_updater.py       # Main script
├── requirements.txt               # Python dependencies
└── README.md                      # This documentation
```

## Prerequisites

* Python 3.8 or higher
* A Service Account JSON key with **Firebase Remote Config Admin** access
* Network access to call the Firebase Remote Config REST API

## Installation

1. Clone or download this repository.

2. (Optional but recommended) Create and activate a virtual environment:

   **On macOS/Linux:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   **On Windows (PowerShell):**

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   **On Windows (Command Prompt):**

   ```bat
   python -m venv venv
   venv\Scripts\activate.bat
   ```

3. Place your service account key at `credentials/service_account.json`.

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Configuration (`config.json`)

Define one or more targets (Android, iOS) and their version/build settings:

```json
{
  "targets": [
    {
      "os": "Android",             // "Android" or "iOS"
      "previous_version": "1.0.0", // optional; auto-detected if omitted
      "new_version": "1.1.0",      // must be ≥ latest existing version
      "new_build": 1100             // must be > latest existing build
    },
    {
      "os": "iOS",
      "new_version": "1.1.0",
      "new_build": 2100
    }
  ]
}
```

* **previous\_version** (optional): if not set, the script finds the highest existing version for that OS.
* **new\_version**: the version tag in your condition name (e.g. `v1.1.0`).
* **new\_build**: the numeric build identifier (e.g. `1100`).

## Usage

Run the updater from the project root:

```bash
python remote_config_updater.py
```

1. The script fetches the current Remote Config template and ETag.
2. It discovers the latest version/build per OS by parsing existing condition names.
3. It validates that each new version/build is not regressing or colliding.
4. It filters and clones all conditions matching the previous build & OS, renames them, and updates their expressions.
5. It updates each parameter’s `conditionalValues` with the new condition keys.
6. It prints a preview of all new condition names and parameter mappings.
7. It prompts you to confirm before pushing changes back to Firebase.

## How It Works

* **Authentication**: Uses `google-auth` and a Service Account to mint OAuth2 tokens for the Remote Config API.
* **Discovery**: Parses existing condition names matching `v<version> Prod Env - <OS> <build>` to determine the highest version/build.
* **Filtering**: Selects conditions whose expression contains the previous *build number* and `device.os == '<OS>'`.
* **Cloning**: Deep-copies each match, replaces version/build in both name and expression, and appends to the template.
* **Parameter Update**: For every parameter with matching old condition keys, it duplicates the value under the new key.
* **Preview & Confirm**: Lists all proposed changes and waits for `y` confirmation before making a `PUT` request with the original ETag.

## Error Handling and Validations

* Aborts if `new_build` is ≤ the latest existing build for that OS.
* Aborts if `new_version` is less than the latest existing version.
* Exits cleanly if you decline to confirm the preview.

---

*Last updated: May 2025*
