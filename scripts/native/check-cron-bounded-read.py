#!/usr/bin/env python3
"""Run current cursor bounded-read cases with a pinned diagnostic FS2 provider.

Python stages and observes native programs. This is not a release qualification.
"""
import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('decisions', Path(__file__).with_name('check-cron-decisions.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def match_function(unity, path, name):
    raw = path.read_bytes(); source = raw.decode()
    a, b = helper.form(source, name); x, y = helper.form(unity, name)
    if source[a:b] != unity[x:y]: raise ValueError('definition mismatch: ' + name)
    return helper.digest(raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unity', type=Path, required=True); p.add_argument('--unity-sha256', required=True)
    p.add_argument('--checkpoint', type=Path, required=True); p.add_argument('--checkpoint-sha256', required=True)
    p.add_argument('--compiler', type=Path, required=True); p.add_argument('--compiler-sha256', required=True)
    p.add_argument('--packager', type=Path, required=True); p.add_argument('--packager-sha256', required=True)
    a = p.parse_args()
    if (platform.system(), platform.machine()) != ('Darwin', 'arm64'): raise ValueError('Mac ARM64 required')
    if a.unity.is_symlink() or a.checkpoint.is_symlink(): raise ValueError('source symlink refused')
    raw = a.unity.read_bytes(); checkpoint = a.checkpoint.read_bytes()
    if helper.digest(raw) != a.unity_sha256 or helper.digest(checkpoint) != a.checkpoint_sha256:
        raise ValueError('source pin mismatch')
    source = raw.decode()
    compiler = helper.verified(a.compiler, a.compiler_sha256)
    packager = helper.verified(a.packager, a.packager_sha256)
    cursor = ROOT / 'kotoba/itonami/gateway_cursor.kotoba'
    cases = ROOT / 'test/native/gateway_cursor_bounded_cases.kotoba'
    cursor_sha = match_function(source, cursor, 'cc-read-bounded')
    cases_sha = match_function(source, cases, 'test-cursor-bounded-reads')
    for name in ('cp-size', 'cp-range', 'cp-read-op', 'cp-fs', 'cp-frame'):
        match_function(source, a.checkpoint, name)
    i, j = helper.form(source, 'main')
    fixture = source[:i] + '(defn main [] :i64 (if (test-cursor-bounded-reads "/cases") 0 1))' + source[j:]
    x, y = helper.form(fixture, 'cc-read-bounded'); guard = fixture[x:y]; anchor = '(> size maximum)'
    if guard.count(anchor) != 1: raise ValueError('bound control anchor changed')
    mutant = fixture[:x] + guard.replace(anchor, 'false') + fixture[y:]
    with tempfile.TemporaryDirectory(prefix='awai167-bounded-read-', dir='/private/tmp') as tmp:
        root = Path(tmp); scope = root / 'cases'; scope.mkdir(mode=0o700)
        for name, data in [('small', b'ok'), ('cursor-limit', b'x'*1024), ('cursor-over', b'x'*1025),
                           ('definition-limit', b'x'*8192), ('definition-over', b'x'*8193), ('empty', b'')]:
            (scope / name).write_bytes(data)
        (root / 'fixture.kotoba').write_text(fixture); (root / 'mutant.kotoba').write_text(mutant)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY); saved = None
        if fd != 3:
            try: saved = os.dup(3)
            except OSError: pass
            os.dup2(fd, 3)
        try:
            def run(argv, expected=0):
                r = subprocess.run([str(x) for x in argv], cwd=root, pass_fds=(3,), capture_output=True,
                                   timeout=180, env={'PATH': '/nonexistent'})
                if r.returncode != expected or r.stderr:
                    raise RuntimeError((str(argv[0]), r.returncode, r.stdout[-300:], r.stderr[-300:]))
                return r.stdout
            def build(name):
                run([compiler, 'compile', name+'.kotoba', '--target', 'aarch64-macos', '--output', name+'.kseed'])
                out = run([compiler, 'extract-native', name+'.kseed', '--symbol', 'main', '--output', name+'.raw'])
                match = re.search(rb':offset (\d+), :length (\d+), :arity 0}', out)
                if not match or int(match.group(2)) != (root / (name+'.raw')).stat().st_size:
                    raise ValueError('extract mismatch')
                run([packager, name+'-unsigned.macho', name+'.raw', 'fs2-cli-stdio-general', match.group(1).decode()])
                image = root / (name+'.macho'); shutil.copyfile(root / (name+'-unsigned.macho'), image); image.chmod(0o700)
                subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(image)], check=True, capture_output=True, timeout=30)
                subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(image)], check=True, capture_output=True, timeout=30)
                return image
            run([build('fixture')]); run([build('mutant')], 1)
            if (helper.digest(cursor.read_bytes()) != cursor_sha or helper.digest(cases.read_bytes()) != cases_sha or
                    helper.digest(a.checkpoint.read_bytes()) != a.checkpoint_sha256): raise ValueError('source changed')
            print(json.dumps({'unitySha256': a.unity_sha256, 'checkpointSha256': a.checkpoint_sha256,
                              'cursorSha256': cursor_sha, 'casesSha256': cases_sha,
                              'fixtureSha256': helper.digest(fixture.encode()), 'compilerSha256': a.compiler_sha256,
                              'packagerSha256': a.packager_sha256, 'nativeExit': 0, 'boundMutantExit': 1,
                              'scope': 'diagnostic bounded FS2 reads; not provider or governor qualification'}))
        finally:
            if fd != 3:
                if saved is None: os.close(3)
                else: os.dup2(saved, 3); os.close(saved)
            os.close(fd)


if __name__ == '__main__': main()
