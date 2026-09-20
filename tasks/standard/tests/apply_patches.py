#!/usr/bin/env python3
"""Apply ordinary Git code/test patch hunks to each checkout listed in the manifest."""
import argparse
import json
from pathlib import Path
import subprocess

def apply_layer(repo, package, meta, kind, env=None, cached=False):
    def git(*args, input=None):
        return subprocess.check_output(['git', '-C', str(repo), *args], env=env, input=input)
    layer = meta[f'{kind}_patch']
    args = ['apply', '--unidiff-zero', '--whitespace=nowarn']
    if cached:
        args.append('--cached')
    else:
        git('update-index', '--refresh')
        args.append('--index')
    git(*args, str(package / layer['path']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('layer', choices=['code', 'test'])
    parser.add_argument('--workspace', type=Path, default=Path('/workspace'))
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.manifest or args.package / 'patch_manifest.json').read_text())
    for name, meta in manifest['repos'].items():
        apply_layer(args.workspace / name, args.package, meta, args.layer)
        print(f'{name}: applied {args.layer}')


if __name__ == '__main__':
    main()
