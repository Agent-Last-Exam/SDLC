#!/usr/bin/env bash
set -euo pipefail
python3 /solution/apply_patches.py code --workspace /workspace --package / --manifest /solution/patch_manifest.json
# Dependencies stay fixed in the image; start/rebuild services after applying source changes.
