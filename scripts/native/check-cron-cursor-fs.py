#!/usr/bin/env python3
"""Observe current cursor advance and reconciliation on a private Mac FS2 root.

Selected source and diagnostic tools are pinned. This does not exercise the
host lock, GitHub archive, leases, power loss, or production qualification.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
import platform
import re
import select
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bounded',Path(__file__).with_name('check-cron-bounded-read.py'))
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
helper=mod.helper


def cid(data):
    return 'b'+base64.b32encode(b'\x01\x55\x12\x20'+hashlib.sha256(data).digest()).decode().lower().rstrip('=')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unity',type=Path,required=True); p.add_argument('--unity-sha256',required=True)
    p.add_argument('--checkpoint',type=Path,required=True); p.add_argument('--checkpoint-sha256',required=True)
    p.add_argument('--compiler',type=Path,required=True); p.add_argument('--compiler-sha256',required=True)
    p.add_argument('--packager',type=Path,required=True); p.add_argument('--packager-sha256',required=True)
    a=p.parse_args()
    if (platform.system(),platform.machine())!=('Darwin','arm64'): raise ValueError('Mac ARM64 required')
    if a.unity.is_symlink() or a.checkpoint.is_symlink(): raise ValueError('source symlink refused')
    raw=a.unity.read_bytes(); checkpoint=a.checkpoint.read_bytes()
    if helper.digest(raw)!=a.unity_sha256 or helper.digest(checkpoint)!=a.checkpoint_sha256: raise ValueError('source pin mismatch')
    source=raw.decode(); compiler=helper.verified(a.compiler,a.compiler_sha256); packager=helper.verified(a.packager,a.packager_sha256)
    cursor=ROOT/'kotoba/itonami/gateway_cursor.kotoba'
    for name in ('cc-cursor','cc-read-bounded','cc-advance','cc-recovery-ready?','cc-recover',
                 'cc-turn-text','cc-turn-begin','cc-turn-finalize'):
        cursor_sha=mod.match_function(source,cursor,name)
    for name in ('cp-size','cp-range','cp-read-op','cp-fs','cp-frame','cp-write','cp-written-equal?','cp-parent-dir'):
        mod.match_function(source,a.checkpoint,name)
    i,j=helper.form(source,'main')
    entry='''(defn main [] :i64
      (let [op (cp-arg 0) path (cp-arg 1)
            result (cond (= op "advance") (cc-advance path (cp-bytes (cp-arg 2)) "pin" 60000)
                         (= op "recover") (cc-recover path (cc-read-bounded path 1024))
                         (= op "turn-begin") (if (cc-turn-begin path "pin" (cp-bytes "original") "job-id" 60000 "/lock" "/token" "1001,1002" "node-a" "did:test") "turn/begun" "turn/unknown")
                         (= op "turn-finalize") (if (cc-turn-finalize path) "turn/finalized" "turn/unknown")
                         :else "invalid")
            printed (cp-say result)]
        (if (or (= result "cursor/advanced") (= result "cursor/recovered") (= result "turn/begun") (= result "turn/finalized")) 0 1)))'''
    fixture=(source[:i]+entry+source[j:]).encode()
    with tempfile.TemporaryDirectory(prefix='awai167-cursor-fs-',dir='/private/tmp') as tmp:
        root=Path(tmp); q=root/'cases'; q.mkdir(mode=0o700); (root/'fixture.kotoba').write_bytes(fixture)
        source_fixture=fixture.decode(); start,end=helper.form(source_fixture,'cc-advance')
        advance=source_fixture[start:end]
        pause=('(defn- cc-test-pause [] :bool\n'
               '  (let [v (vector-alloc 262144) s (string-from-utf8 (bytes-from-vector-i64 v))\n'
               '        sent (typed-cap-call 37 :string :string s)] true))\n')
        points={
            'after-intent-sync': '(not (= (cp-fs "M" dir "") "1")) "cursor/intent-unknown"',
            'after-pending': '(not (cp-write tmp (cc-cursor pin slot))) "cursor/write-unknown"',
            'after-rename': '(not (= (cp-fs "L" tmp path) "1")) "cursor/rename-unknown"',
            'after-cursor-sync': '(not (= (cp-fs "M" dir "") "1")) "cursor/fsync-unknown"',
            'after-archive': '(not (= (cp-fs "L" intent (str path ".last")) "1")) "cursor/intent-unknown"',
        }
        for phase,anchor in points.items():
            if advance.count(anchor)!=(2 if phase=='after-intent-sync' else 1):
                raise ValueError('pause anchor changed: '+phase)
            changed=advance.replace(anchor,anchor+'\n          (not (cc-test-pause)) "cursor/test-pause-failed"',1)
            (root/(phase+'.kotoba')).write_text(source_fixture[:start]+pause+changed+source_fixture[end:])
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY); saved=None
        if fd!=3:
            try: saved=os.dup(3)
            except OSError: pass
            os.dup2(fd,3)
        try:
            def run(argv,expected=0):
                r=subprocess.run([str(x) for x in argv],cwd=root,pass_fds=(3,),capture_output=True,
                                 timeout=180,env={'PATH':'/nonexistent'})
                if r.returncode!=expected or r.stderr: raise RuntimeError((str(argv[0]),r.returncode,r.stdout[-300:],r.stderr[-300:]))
                return r.stdout
            def build(name):
                run([compiler,'compile',name+'.kotoba','--target','aarch64-macos','--output',name+'.kseed'])
                out=run([compiler,'extract-native',name+'.kseed','--symbol','main','--output',name+'.raw'])
                m=re.search(rb':offset (\d+), :length (\d+), :arity 0}',out)
                if not m or int(m.group(2))!=(root/(name+'.raw')).stat().st_size: raise ValueError('extract mismatch')
                run([packager,name+'-unsigned.macho',name+'.raw','fs2-cli-stdio-general',m.group(1).decode()])
                image=root/(name+'.macho'); shutil.copyfile(root/(name+'-unsigned.macho'),image); image.chmod(0o700)
                subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(image)],check=True,capture_output=True,timeout=30)
                subprocess.run(['/usr/bin/codesign','--verify','--strict',str(image)],check=True,capture_output=True,timeout=30)
                return image
            image=build('fixture')
            def expect(op,name,value,expected,code):
                result=run([image,op,'/cases/'+name,value],code).decode()
                if result!=expected+'\n': raise ValueError((op,name,result))
            old=b'original'; new=b'{"kind":"itonami.cron-cursor/1","schedule":"pin","slot":60000}'
            (q/'ok').write_bytes(old); expect('advance','ok','original','cursor/advanced',0)
            if (q/'ok').read_bytes()!=new or (q/'ok.pending').exists() or (q/'ok.intent').exists():
                raise ValueError('advance state mismatch')
            journal=('itc1\n'+cid(old)+'\n'+cid(new)+'\n').encode()
            if (q/'ok.last').read_bytes()!=journal: raise ValueError('advance journal mismatch')
            (q/'changed').write_bytes(b'different'); expect('advance','changed','original','cursor/changed',1)
            if (q/'changed').read_bytes()!=b'different' or not (q/'changed.pending').exists() or not (q/'changed.intent').exists():
                raise ValueError('changed state mismatch')
            (q/'pending').write_bytes(old); (q/'pending.pending').write_bytes(b'sentinel')
            expect('advance','pending','original','cursor/pending-unknown',1)
            if (q/'pending.pending').read_bytes()!=b'sentinel': raise ValueError('pending overwritten')
            (q/'recover').write_bytes(new); (q/'recover.intent').write_bytes(journal)
            expect('recover','recover','','cursor/recovered',0)
            if (q/'recover').read_bytes()!=new or (q/'recover.intent').exists() or (q/'recover.last').read_bytes()!=journal:
                raise ValueError('recovery state mismatch')
            (q/'old').write_bytes(old); (q/'old.intent').write_bytes(journal)
            expect('recover','old','','cursor/recovery-unknown',1)
            (q/'blocked').write_bytes(new); (q/'blocked.intent').write_bytes(journal); (q/'blocked.pending').write_bytes(b'x')
            expect('recover','blocked','','cursor/recovery-unknown',1)
            (q/'malformed').write_bytes(new); (q/'malformed.intent').write_bytes(b'broken')
            expect('recover','malformed','','cursor/recovery-unknown',1)
            for name in ('old','blocked','malformed'):
                if not (q/(name+'.intent')).exists(): raise ValueError('unknown intent lost')
            expect('turn-begin','turn','','turn/begun',0)
            h=lambda value: hashlib.sha256(value.encode()).hexdigest()
            turn=('jti4\npin\n'+cid(old)+'\njob-id\n60000\n'+h('/lock')+'\n'+h('/token')+'\n'+
                  h('1001,1002')+'\n'+h('node-a')+'\n'+h('did:test')+'\n').encode()
            if (q/'turn.turn-intent').read_bytes()!=turn: raise ValueError('turn intent binding mismatch')
            expect('turn-begin','turn','','turn/unknown',1)
            if (q/'turn.turn-intent').read_bytes()!=turn: raise ValueError('turn intent overwritten')
            expect('turn-finalize','turn','','turn/finalized',0)
            if (q/'turn.turn-intent').exists() or (q/'turn.turn-last').read_bytes()!=turn:
                raise ValueError('turn finalization mismatch')
            killed=[]
            for phase in points:
                name='kill-'+phase; (q/name).write_bytes(old); variant=build(phase)
                child=subprocess.Popen([str(variant),'advance','/cases/'+name,'original'],cwd=root,pass_fds=(3,),
                                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/nonexistent'})
                try:
                    if not select.select([child.stdout],[],[],10)[0] or os.read(child.stdout.fileno(),1)!=b'\0':
                        raise RuntimeError('pause not reached: '+phase)
                    if child.poll() is not None: raise ValueError('child exited before kill')
                    changed=phase in ('after-rename','after-cursor-sync','after-archive')
                    if (q/name).read_bytes()!=(new if changed else old): raise ValueError('cursor mismatch: '+phase)
                    if (q/(name+'.intent')).exists() != (phase!='after-archive'): raise ValueError('intent mismatch: '+phase)
                    if (q/(name+'.pending')).exists() != (phase=='after-pending'): raise ValueError('pending mismatch: '+phase)
                    if (q/(name+'.last')).exists() != (phase=='after-archive'): raise ValueError('archive mismatch: '+phase)
                    child.kill()
                    if child.wait(timeout=3)!=-9: raise ValueError('child kill status mismatch')
                    expected='cursor/recovered' if phase in ('after-rename','after-cursor-sync') else 'cursor/recovery-unknown'
                    expect('recover',name,'',expected,0 if expected=='cursor/recovered' else 1)
                    if (q/name).read_bytes()!=(new if changed else old): raise ValueError('recovery changed cursor')
                    killed.append(phase)
                finally:
                    if child.poll() is None: child.kill(); child.wait(timeout=3)
            if helper.digest(cursor.read_bytes())!=cursor_sha or helper.digest(a.checkpoint.read_bytes())!=a.checkpoint_sha256:
                raise ValueError('source changed')
            print(json.dumps({'unitySha256':a.unity_sha256,'checkpointSha256':a.checkpoint_sha256,
                              'cursorSha256':cursor_sha,'fixtureSha256':helper.digest(fixture),
                              'compilerSha256':a.compiler_sha256,'packagerSha256':a.packager_sha256,
                              'advance':True,'changedAndPendingRefused':True,'completedRecovery':True,
                              'oldPendingMalformedRecoveryUnknown':True,
                              'turnIntentBindingAndDuplicateRefusal':True,
                              'ownedChildKillPhases':killed,
                              'scope':'private local FS2; no GitHub, lock, crash or governor qualification'}))
        finally:
            if fd!=3:
                if saved is None: os.close(3)
                else: os.dup2(saved,3); os.close(saved)
            os.close(fd)


if __name__=='__main__': main()
