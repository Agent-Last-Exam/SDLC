"""Apply candidate changes in a fresh separate verifier and restore official tests.
The test image starts at C; reset to the recorded base before applying base-relative model patches.
"""
import json
from pathlib import Path
import subprocess

from apply_patches import apply_layer

manifest=json.loads(Path('/tests/patch_manifest.json').read_text())
for name,meta in manifest['repos'].items():
    repo=Path('/workspace')/name
    def git(*args):
        return subprocess.check_output(['git','-C',str(repo),*args],text=True)
    git('reset','--hard',meta['sha_base'])
    git('apply','--index','--whitespace=nowarn','--allow-empty',f'/logs/artifacts/{name}.model.patch')
    test_patch=Path('/')/meta['test_patch']['path']
    paths=[line.split('\t',2)[2] for line in git('apply','--numstat',str(test_patch)).splitlines()]
    base_paths=set(git('ls-tree','-r','--name-only',meta['sha_base']).splitlines())
    old=[p for p in paths if p in base_paths]
    new=[p for p in paths if p not in base_paths]
    git('restore','--source='+meta['sha_base'],'--staged','--worktree','--',*old)
    git('rm','--force','--ignore-unmatch','--',*new)
    apply_layer(repo,Path('/'),meta,'test')
