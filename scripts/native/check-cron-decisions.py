#!/usr/bin/env python3
"""Run source-bound cron decision cases natively, with no live effects.

The supplied unity is a caller-pinned selected composition, not a release
closure. Python stages and observes the native programs only.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = {'test-cron-cursor':'gateway_cursor_cases.kotoba',
         'test-guarded-cron-cursor':'gateway_guarded_job_node_cases.kotoba',
         'test-job-archive-cursor':'gateway_job_archive_cursor_cases.kotoba'}


def digest(b): return hashlib.sha256(b).hexdigest()


def form(source, name):
    matches = list(re.finditer(r'(?m)^\(defn-?\s+' + re.escape(name) + r'(?=\s|\[)', source))
    if len(matches) != 1: raise ValueError('missing or duplicate definition: '+name)
    start = matches[0].start(); depth = 0; quoted = False; escape = False; comment = False
    for i in range(start, len(source)):
        c = source[i]
        if comment:
            if c == '\n': comment = False
        elif quoted:
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == '"': quoted = False
        elif c == ';': comment = True
        elif c == '"': quoted = True
        elif c == '(': depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: return start, i+1
    raise ValueError('unterminated definition: '+name)


def verified(path, pin):
    if path.is_symlink() or not re.fullmatch('[0-9a-f]{64}', pin): raise ValueError('bad image or pin')
    path = path.resolve(strict=True)
    if digest(path.read_bytes()) != pin: raise ValueError('image pin mismatch')
    subprocess.run(['/usr/bin/codesign','--verify','--strict',str(path)],check=True,capture_output=True,timeout=30)
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unity',required=True,type=Path); p.add_argument('--unity-sha256',required=True)
    p.add_argument('--compiler',required=True,type=Path); p.add_argument('--compiler-sha256',required=True)
    p.add_argument('--packager',required=True,type=Path); p.add_argument('--packager-sha256',required=True)
    a=p.parse_args()
    if (platform.system(),platform.machine()) != ('Darwin','arm64'): raise ValueError('Mac ARM64 required')
    compiler=verified(a.compiler,a.compiler_sha256); packager=verified(a.packager,a.packager_sha256)
    if a.unity.is_symlink(): raise ValueError('unity symlink refused')
    raw=a.unity.read_bytes()
    if digest(raw)!=a.unity_sha256: raise ValueError('unity pin mismatch')
    source=raw.decode(); case_pins={}
    for name,file in CASES.items():
        case=(ROOT/'test/native'/file).read_bytes(); expected=case.decode()
        i,j=form(expected,name); x,y=form(source,name)
        if expected[i:j] != source[x:y]: raise ValueError('case does not match checkout: '+name)
        case_pins[file]=digest(case)
    i,j=form(source,'main')
    main='(defn main [] :i64 (if (and (test-cron-cursor) (test-guarded-cron-cursor) (test-job-archive-cursor)) 0 1))'
    fixture=(source[:i]+main+source[j:]).encode()
    text=fixture.decode(); x,y=form(text,'cjg-cursor-problem')
    guard=text[x:y]; anchor='(not (= pending "0"))'
    if guard.count(anchor)!=1: raise ValueError('pending negative control changed')
    mutant=(text[:x]+guard.replace(anchor,'false')+text[y:]).encode()
    with tempfile.TemporaryDirectory(prefix='awai167-cron-decision-',dir='/private/tmp') as tmp:
        root=Path(tmp); (root/'fixture.kotoba').write_bytes(fixture)
        (root/'mutant.kotoba').write_bytes(mutant)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY); saved=None
        if fd!=3:
            try: saved=os.dup(3)
            except OSError: pass
            os.dup2(fd,3)
        try:
            def run(argv,expected=0):
                r=subprocess.run([str(x) for x in argv],cwd=root,pass_fds=(3,),capture_output=True,
                                 timeout=180,env={'PATH':'/nonexistent'})
                if r.returncode!=expected or r.stderr:
                    raise RuntimeError((str(argv[0]),r.returncode,r.stdout[-300:],r.stderr[-300:]))
                return r.stdout
            def build(name):
                run([compiler,'compile',name+'.kotoba','--target','aarch64-macos','--output',name+'.kseed'])
                extracted=run([compiler,'extract-native',name+'.kseed','--symbol','main','--output',name+'.raw'])
                match=re.search(rb':offset (\d+), :length (\d+), :arity 0}',extracted)
                if not match or int(match.group(2))!=(root/(name+'.raw')).stat().st_size: raise ValueError('extract mismatch')
                run([packager,name+'-unsigned.macho',name+'.raw','fs2-cli-stdio-general',match.group(1).decode()])
                image=root/(name+'.macho'); shutil.copyfile(root/(name+'-unsigned.macho'),image); image.chmod(0o700)
                subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(image)],check=True,capture_output=True,timeout=30)
                subprocess.run(['/usr/bin/codesign','--verify','--strict',str(image)],check=True,capture_output=True,timeout=30)
                return image
            run([build('fixture')]); run([build('mutant')],1)
            if digest(compiler.read_bytes())!=a.compiler_sha256 or digest(packager.read_bytes())!=a.packager_sha256:
                raise ValueError('tool changed')
            print(json.dumps({'unitySha256':digest(raw),'fixtureSha256':digest(fixture),'caseSha256':case_pins,
                              'compilerSha256':a.compiler_sha256,'packagerSha256':a.packager_sha256,
                              'nativeExit':0,'pendingGuardMutantExit':1,
                              'scope':'pure decision cases only; no live side effects'}))
        finally:
            if fd!=3:
                if saved is None: os.close(3)
                else: os.dup2(saved,3); os.close(saved)
            os.close(fd)


if __name__=='__main__': main()
