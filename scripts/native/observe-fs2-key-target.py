#!/usr/bin/env python3
"""Observe pinned key diagnostics with public synthetic data only."""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True); p.add_argument('--manifest-sha256',required=True)
    a=p.parse_args()
    if (platform.system(),platform.machine())!=('Darwin','arm64'): raise ValueError('Mac ARM64 required')
    build=subprocess.run(['/usr/bin/sw_vers','-buildVersion'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    if build!='25G332': raise ValueError('unexpected host build')
    if a.artifacts.is_symlink() or not re.fullmatch('[0-9a-f]{64}',a.manifest_sha256): raise ValueError('bad input')
    root=a.artifacts.resolve(strict=True); manifest_path=root/'manifest.json'
    if manifest_path.is_symlink(): raise ValueError('manifest symlink refused')
    raw=manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=a.manifest_sha256: raise ValueError('manifest mismatch')
    manifest=json.loads(raw); pins=manifest.get('images',{})
    if set(pins)!={'fs2keyprobe','didprobe'}: raise ValueError('unexpected images')
    images={}
    for name,pin in pins.items():
        path=root/(name+'.macho')
        if path.is_symlink() or not re.fullmatch('[0-9a-f]{64}',pin) or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:
            raise ValueError('image mismatch')
        subprocess.run(['/usr/bin/codesign','--verify','--strict',str(path)],check=True,capture_output=True,timeout=30)
        images[name]=path
    with tempfile.TemporaryDirectory(prefix='awai167-key-target-') as tmp:
        scope=Path(tmp)
        for name,value in [('key','00'*32+'\n'),('short','0'*63),('invalid','z'*64),('long','00'*32+'x'*8192)]:
            path=scope/name; path.write_text(value); path.chmod(0o600)
        fd=os.open(scope,os.O_RDONLY|os.O_DIRECTORY); saved=None
        if fd!=3:
            try: saved=os.dup(3)
            except OSError: pass
            os.dup2(fd,3)
        try:
            def run(image,name,expected):
                r=subprocess.run([str(images[image]),'/'+name],cwd=scope,pass_fds=(3,),capture_output=True,
                                 timeout=20,env={'PATH':'/nonexistent'})
                if r.returncode!=expected or r.stdout or r.stderr: raise RuntimeError((image,name,r.returncode,len(r.stdout),len(r.stderr)))
            run('fs2keyprobe','key',0); run('didprobe','key',0)
            run('fs2keyprobe','short',1); run('fs2keyprobe','invalid',1); run('fs2keyprobe','missing',1)
            run('fs2keyprobe','long',0)
        finally:
            if fd!=3:
                if saved is None: os.close(3)
                else: os.dup2(saved,3); os.close(saved)
            os.close(fd)
    print(json.dumps({'build':build,'manifestSha256':a.manifest_sha256,'syntheticKeyAndDid':True,
                      'shortInvalidMissingRefused':True,'longPrefixAccepted':True,'governorQualified':False}))


if __name__=='__main__': main()
