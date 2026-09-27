"""Add base-only Node packages to the target-locked dependency tree."""
import json
from pathlib import Path
import shutil

base_modules=Path('/opt/base-node-modules')
modules=Path('/workspace/saleor-dashboard/node_modules')
added_node=[]
base_bins=base_modules/'.bin'
target_bins=modules/'.bin'
for entry in base_bins.iterdir():
    destination=target_bins/entry.name
    if destination.exists() or destination.is_symlink():
        continue
    destination.symlink_to(entry.readlink())
for entry in base_modules.iterdir():
    if entry.name.startswith('.'):
        continue
    packages=list(entry.iterdir()) if entry.name.startswith('@') else [entry]
    for package in packages:
        relative=package.relative_to(base_modules)
        destination=modules/relative
        if destination.exists():
            continue
        shutil.copytree(package,destination,symlinks=True)
        added_node.append(str(relative))
Path('/opt/runtime/dependency-union.json').write_text(json.dumps({
    'strategy': 'base dependencies upgraded by target lockfiles; base-only packages retained',
    'target_manifests': '/opt/environment/dependencies/manifest.json',
    'added_base_only_node': sorted(added_node),
}, indent=2) + '\n')
