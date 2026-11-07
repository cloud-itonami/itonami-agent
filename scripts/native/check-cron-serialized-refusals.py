#!/usr/bin/env python3
"""Exercise the real serialized cron refusal entry using disposable FS2 files.

Clock and job body are test stubs; this does not prove successful dispatch,
workload lifetime, leases, GitHub, production host or resource governance.
"""
import argparse
import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('decisions',Path(__file__).with_name('check-cron-decisions.py'))
helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unity',type=Path,required=True); p.add_argument('--unity-sha256',required=True)
    p.add_argument('--compiler',type=Path,required=True); p.add_argument('--compiler-sha256',required=True)
    p.add_argument('--packager',type=Path,required=True); p.add_argument('--packager-sha256',required=True)
    p.add_argument('--artifact-dir',type=Path,help='optional new directory for diagnostic key probes')
    p.add_argument('--murakumo',type=Path,required=True,help='checkout containing the source for lease and job entry')
    a=p.parse_args()
    if (platform.system(),platform.machine())!=('Darwin','arm64'): raise ValueError('Mac ARM64 required')
    if a.unity.is_symlink(): raise ValueError('unity symlink refused')
    raw=a.unity.read_bytes()
    if helper.digest(raw)!=a.unity_sha256: raise ValueError('unity hash mismatch')
    source=raw.decode(); current=(ROOT/'kotoba/itonami/gateway_guarded_job_node.kotoba').read_text()
    for name in ('cjg-run','cjg-cursor-problem','cron-serialized-job-node-main'):
        i,j=helper.form(current,name); x,y=helper.form(source,name)
        if current[i:j]!=source[x:y]: raise ValueError('guard source mismatch: '+name)
    for filename,names in (('fleet_lease_node.kotoba',('ln-bytes','ln-frame','ln-fs','ln-int','ln-field','ln-exists?','ln-space?','ln-token','lease-token','lease-token-bounded')),
                           ('fleet_job_node.kotoba',('jn-token','jn-token-bounded','jn-run-with-verified-input'))):
        current_m=(a.murakumo/'kotoba'/filename).read_text()
        for name in names:
            i,j=helper.form(current_m,name); x,y=helper.form(source,name)
            if current_m[i:j]!=source[x:y]: raise ValueError('Murakumo source mismatch: '+name)
    replacements={
        'ln-now':'(defn- ln-now [s :string] :i64 1792638000000)',
        'jn-run-with-verified-input':'(defn- jn-run-with-verified-input [source :string source-admitted :bool verified-input :string use-verified-input :bool expected-signer :string] :i64 (let [w (cp-write "/case/dispatched" (cp-bytes "unexpected"))] 0))',
        'main':'(defn main [] :i64 (cron-serialized-job-node-main))',
    }
    edits=[]
    for name,replacement in replacements.items():
        i,j=helper.form(source,name); edits.append((i,j,replacement))
    for i,j,replacement in sorted(edits,reverse=True): source=source[:i]+replacement+source[j:]
    x,y=helper.form(source,'cjg-cursor-problem'); guard=source[x:y]; anchor='(not (= turn "0"))'
    if guard.count(anchor)!=1: raise ValueError('turn guard control changed')
    mutant=source[:x]+guard.replace(anchor,'false')+source[y:]
    positive_replacements={
        'cc-plan-problem':'(defn- cc-plan-problem [definition :vector-i64 pin :string cursor :vector-i64 now :i64] :string "trigger/ok")',
        'cj-problem':'(defn- cj-problem [now :i64 previous :i64 pin :string definition :vector-i64 profile :string input :string policy :string rail :string wrapper :vector-i64 source :vector-i64] :string "consume/ok")',
        'next-cron-ms':'(defn next-cron-ms [e :string after-ms :i64 offset :i64] :i64 60000)',
        'verified-cron-job-id':'(defn verified-cron-job-id [active :bool now :i64 previous :i64 slot :i64 expected :string definition :vector-i64] :string "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")',
        'key-seed':'(defn key-seed [key-path :string] :vector-i64 [1])',
        'key-seed-fs2':'(defn key-seed-fs2 [key-path :string] :vector-i64 [1])',
        'node-did':'(defn node-did [seed :vector-i64] :string "did:test")',
        'jn-run-with-verified-input':'(defn- jn-run-with-verified-input [source :string source-admitted :bool verified-input :string use-verified-input :bool expected-signer :string] :i64 (if (and source-admitted use-verified-input (= source "source") (= verified-input "wrapper") (= expected-signer "did:test") (= (cp-fs "D" "/case/cursor.turn-intent" "") "1") (cp-write "/case/dispatched" (cp-bytes "called"))) 0 1))',
    }
    positive=source; edits=[]
    for name,replacement in positive_replacements.items():
        i,j=helper.form(positive,name); edits.append((i,j,replacement))
    for i,j,replacement in sorted(edits,reverse=True): positive=positive[:i]+replacement+positive[j:]
    setup_entry='''(defn main [] :i64
      (if (= (cp-arg 0) "setup")
        (let [slot 1792638000000 previous (- slot 60000) source (gt-bytes "bounded source")
              definition (test-definition-source "* * * * *" "node-test" 540 (test-pin source))
              pin (test-pin definition) wrapper (gt-bytes (verified-cron-input true slot previous slot pin definition))
              input (verified-cron-input-cid true slot previous slot pin definition)
              job (verified-cron-job-id true slot previous slot pin definition)
              ok (and (cp-write "/case/definition" definition) (cp-write "/case/source" source)
                      (cp-write "/case/input" wrapper) (cp-write "/case/cursor" (cc-cursor pin previous)))
              printed (if ok (cp-say (str pin " " input " " job)) 1)]
          (if ok 0 1))
        (cron-serialized-job-node-main)))'''
    real_stubs={
        'jn-run-with-verified-input':'(defn- jn-run-with-verified-input [source :string source-admitted :bool verified-input :string use-verified-input :bool expected-signer :string] :i64 (if (and source-admitted use-verified-input (= source "bounded source") (= verified-input (cp-text (cc-read-bounded "/case/input" 8192))) (= expected-signer "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp") (= (cp-fs "D" "/case/cursor.turn-intent" "") "1") (cp-write "/case/dispatched" (cp-bytes "called"))) 0 1))',
        'main':setup_entry,
    }
    realplan=source; edits=[]
    for name,replacement in real_stubs.items():
        i,j=helper.form(realplan,name); edits.append((i,j,replacement))
    for i,j,replacement in sorted(edits,reverse=True): realplan=realplan[:i]+replacement+realplan[j:]
    i,j=helper.form(source,'main')
    tokenprobe=source[:i]+'(defn main [] :i64 (if (= (lease-token-bounded (cp-arg 0)) (if (= (cp-arg 1) "empty") "" (if (= (cp-arg 1) "long") (cp-text (cp-read "/case/expected-long")) "abcdefghijklmnopqrstuvwxyz012345"))) 0 1))'+source[j:]
    x,y=helper.form(tokenprobe,'lease-token-bounded'); tokenbody=tokenprobe[x:y]
    token_read='(ln-fs "E" path (str "0:" n))'
    token_length='(= count n)'
    token_recheck='(= (ln-fs "O" path "") meta)'
    if tokenbody.count(token_read)!=1 or tokenbody.count(token_length)!=1 or tokenbody.count(token_recheck)!=1:
        raise ValueError('bounded token guard changed')
    token_short=tokenprobe[:x]+tokenbody.replace(token_read,'(ln-fs "E" path (str "0:" (- n 1)))')+tokenprobe[y:]
    x,y=helper.form(token_short,'lease-token-bounded'); body=token_short[x:y]
    token_short_mutant=token_short[:x]+body.replace(token_length,'true')+token_short[y:]
    x,y=helper.form(tokenprobe,'lease-token-bounded')
    token_changed=tokenprobe[:x]+tokenbody.replace(token_recheck,'false')+tokenprobe[y:]
    meta_call='(ln-fs "O" path "")'
    if tokenbody.count(meta_call)!=2: raise ValueError('bounded token metadata calls changed')
    token_meta=tokenprobe[:x]+tokenbody.replace(meta_call,'(cp-arg 2)')+tokenprobe[y:]
    keyprobe=source[:i]+'(defn main [] :i64 (if (= (vector-count (cr-read "/case/key")) 65) 0 1))'+source[j:]
    fs2keyprobe=source[:i]+'(defn main [] :i64 (if (= (vector-count (key-seed-fs2 (cp-arg 0))) 32) 0 1))'+source[j:]
    didprobe=source[:i]+'(defn main [] :i64 (let [k (key-seed-fs2 (cp-arg 0))] (if (and (= (vector-count k) 32) (= (node-did k) "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp")) 0 1)))'+source[j:]
    x,y=helper.form(fs2keyprobe,'cr-key-meta')
    metaprobe=fs2keyprobe[:x]+'(defn- cr-key-meta [path :string] :string (cp-arg 1))'+fs2keyprobe[y:]
    x,y=helper.form(metaprobe,'cr-read-fs2-key'); keybody=metaprobe[x:y]
    digits='(cr-key-digits? mode 3)'
    if keybody.count(digits)!=1: raise ValueError('key metadata guard changed')
    metamuser=metaprobe[:x]+keybody.replace(digits,'true')+metaprobe[y:]
    meta_check='(= (cr-key-meta path) meta)'
    if keybody.count(meta_check)!=1: raise ValueError('key metadata recheck changed')
    changedmeta=metaprobe[:x]+keybody.replace(meta_check,'false')+metaprobe[y:]
    frame=r'(typed-cap-call :fs/app-data :string :bytes (str "\u0000FS2\u0000E" path "\u00000:64"))'
    if keybody.count(frame)!=1: raise ValueError('key response anchor changed')
    shortframe=metaprobe[:x]+keybody.replace(frame,'(bytes-from-vector-i64 [0 70 83 50 0])')+metaprobe[y:]
    original=raw.decode(); x,y=helper.form(original,'jn-run-with-verified-input'); job_entry=original[x:y]
    clock='(jn-int (typed-cap-call 7 :string :string "wall"))'
    if job_entry.count(clock)!=1: raise ValueError('job clock anchor changed')
    job_entry=job_entry.replace(clock,'1792638000000')
    x,y=helper.form(source,'jn-run-with-verified-input'); jnprobe=source[:x]+job_entry+source[y:]
    x,y=helper.form(jnprobe,'main')
    jnprobe=jnprobe[:x]+'(defn main [] :i64 (jn-run-with-verified-input "bounded source" true "wrapper" true "did:wrong"))'+jnprobe[y:]
    compiler=helper.verified(a.compiler,a.compiler_sha256); packager=helper.verified(a.packager,a.packager_sha256)
    with tempfile.TemporaryDirectory(prefix='awai167-serialized-',dir='/private/tmp') as tmp:
        root=Path(tmp); case=root/'case'; case.mkdir(mode=0o700)
        (case/'cron.lock').write_text(''); (case/'cron.lock').chmod(0o600)
        (case/'definition').write_text('{}'); (case/'cursor').write_text('{}')
        (root/'fixture.kotoba').write_text(source)
        (root/'mutant.kotoba').write_text(mutant)
        (root/'positive.kotoba').write_text(positive)
        (root/'realplan.kotoba').write_text(realplan)
        (root/'keyprobe.kotoba').write_text(keyprobe)
        (root/'tokenprobe.kotoba').write_text(tokenprobe)
        (root/'token-short.kotoba').write_text(token_short)
        (root/'token-short-mutant.kotoba').write_text(token_short_mutant)
        (root/'token-changed.kotoba').write_text(token_changed)
        (root/'token-meta.kotoba').write_text(token_meta)
        (root/'fs2keyprobe.kotoba').write_text(fs2keyprobe)
        (root/'didprobe.kotoba').write_text(didprobe)
        (root/'metaprobe.kotoba').write_text(metaprobe)
        (root/'metamutant.kotoba').write_text(metamuser)
        (root/'changedmeta.kotoba').write_text(changedmeta)
        (root/'shortframe.kotoba').write_text(shortframe)
        (root/'jnprobe.kotoba').write_text(jnprobe)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY); saved=None
        if fd!=3:
            try: saved=os.dup(3)
            except OSError: pass
            os.dup2(fd,3)
        try:
            def run(argv,expected=0):
                r=subprocess.run([str(x) for x in argv],cwd=root,pass_fds=(3,),capture_output=True,timeout=180,
                                 env={'PATH':'/nonexistent'})
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
            image=build('fixture'); mutant_image=build('mutant'); positive_image=build('positive'); realplan_image=build('realplan'); key_image=build('keyprobe'); token_image=build('tokenprobe'); fs2key_image=build('fs2keyprobe'); did_image=build('didprobe'); jn_image=build('jnprobe')
            token_short_image=build('token-short'); token_short_mutant_image=build('token-short-mutant'); token_changed_image=build('token-changed'); token_meta_image=build('token-meta')
            meta_image=build('metaprobe'); metam_image=build('metamutant'); changed_image=build('changedmeta'); short_image=build('shortframe')
            args=['run-cron','profile','input','policy','rail','node-a','/case/key','fd','admitted','clock',
                  'other','/case/policy','/case/environment','ports','x','y','/case/input','/case/token',
                  '/case/attempts','0','pin','/case/definition','/case/source','capture-output','/case/cursor','/case/cron.lock']
            def expect(message):
                out=run([image,*args],1).decode()
                if out!=message+'\n': raise ValueError(('unexpected response',out,message))
                if (case/'dispatched').exists(): raise ValueError('refusal reached job body')
            with (case/'cron.lock').open('r+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); expect('cron-lock/busy-or-unknown')
            for suffix,message in [('.pending','cron-guard/pending-unknown'),('.intent','cron-guard/intent-unknown'),
                                   ('.head-intent','cron-guard/head-intent-unknown'),('.turn-intent','cron-guard/turn-intent-unknown')]:
                marker=case/('cursor'+suffix); marker.write_text('synthetic')
                expect(message)
                if marker.read_text()!='synthetic': raise ValueError('marker changed')
                marker.unlink()
            expect('cron-guard/plan-refused')
            marker=case/'cursor.turn-intent'; marker.write_text('synthetic')
            if run([mutant_image,*args],1).decode()!='cron-guard/plan-refused\n':
                raise ValueError('turn-guard removal control not detected')
            if marker.read_text()!='synthetic' or (case/'dispatched').exists():
                raise ValueError('negative control changed state')
            marker.unlink()
            cursor=b'{"kind":"itonami.cron-cursor/1","schedule":"pin","slot":0}'
            (case/'cursor').write_bytes(cursor); (case/'source').write_text('source'); (case/'input').write_text('wrapper')
            if run([positive_image,*args])!=b'': raise ValueError('unexpected positive output')
            if (case/'dispatched').read_text()!='called': raise ValueError('job stub did not run')
            cid='b'+base64.b32encode(b'\x01\x55\x12\x20'+hashlib.sha256(cursor).digest()).decode().lower().rstrip('=')
            h=lambda x: hashlib.sha256(x.encode()).hexdigest()
            intent=('jti4\npin\n'+cid+'\n'+'a'*64+'\n60000\n'+h('/case/cron.lock')+'\n'+h('/case/token')+'\n'+
                    h('ports')+'\n'+h('node-a')+'\n'+h('did:test')+'\n')
            if marker.read_text()!=intent: raise ValueError('turn marker binding mismatch')
            (case/'dispatched').write_text('existing')
            if run([positive_image,*args],1).decode()!='cron-guard/turn-intent-unknown\n':
                raise ValueError('duplicate turn was not refused')
            if marker.read_text()!=intent or (case/'dispatched').read_text()!='existing':
                raise ValueError('duplicate turn changed state')
            marker.unlink(); (case/'dispatched').unlink()
            (case/'key').write_text('00'*32+'\n'); (case/'key').chmod(0o600)
            run([key_image],-5)
            (case/'token').write_text('abcdefghijklmnopqrstuvwxyz012345\n')
            (case/'token').chmod(0o600)
            run([token_image,'/case/token'])
            run([token_short_image,'/case/token','empty'])
            run([token_short_mutant_image,'/case/token'])
            run([token_changed_image,'/case/token','empty'])
            run([token_meta_image,'/case/token','normal','384 33 8 0'])
            for metadata in ('', '-0 33 8 0', '512 33 8 0', '384 31 8 0',
                             '384 4097 8 0', '384 33 bad 0', '384 33 8 1',
                             '384 33 8 0 extra', '384 33 8 0 '):
                run([token_meta_image,'/case/token','empty',metadata])
            (case/'short-token').write_text('short')
            run([token_image,'/case/short-token','empty'])
            run([token_image,'/case/missing-token','empty'])
            (case/'expected-long').write_text('a'*4096)
            run([token_image,'/case/expected-long','long'])
            (case/'oversize-token').write_text('a'*4097)
            run([token_image,'/case/oversize-token','empty'])
            (case/'whitespace-token').write_text(' '*4096)
            run([token_image,'/case/whitespace-token','empty'])
            run([fs2key_image,'/case/key'])
            run([did_image,'/case/key'])
            (case/'short-key').write_text('0'*63); run([fs2key_image,'/case/short-key'],1)
            (case/'bad-key').write_text('z'*64); run([fs2key_image,'/case/bad-key'],1)
            (case/'long-key').write_text('00'*32+'x'*8192); run([fs2key_image,'/case/long-key'])
            run([fs2key_image,'/case/missing-key'],1)
            run([meta_image,'/case/key','384 65 8 0'])
            for metadata in ('-0 65 8 0','512 65 8 0','384 63 8 0','384 65 8 1',
                             '384 65 bad 0','384 65 8 0 extra','384 65 8 0 '):
                run([meta_image,'/case/key',metadata],1)
            run([metam_image,'/case/key','-0 65 8 0'])
            run([changed_image,'/case/key','384 65 8 0'],1)
            run([short_image,'/case/key','384 65 8 0'],1)
            setup=run([realplan_image,'setup']).decode().strip().split(' ')
            if len(setup)!=3: raise ValueError('synthetic plan setup failed')
            pin,input_cid,job=setup
            realargs=list(args); realargs[1]='sha256:6e5ac5ef12cd31e4889ec39bc8944e41cbca613829e5dad43c2eb401239c9ea8'
            realargs[2]=input_cid; realargs[3]='bafkreicag2vl77rqrkqabdchmccylgru2qdcqn377gpefuebimv4junsgq'
            realargs[4]='murakumo'; realargs[19]=str(1792638000000-60000); realargs[20]=pin
            jnargs=list(realargs); jnargs[17]=''
            if run([jn_image,*jnargs],1).decode()!='job/signer-changed\n':
                raise ValueError('actual job entry did not derive signer')
            tokenargs=list(jnargs); tokenargs[17]='/case/token'
            if run([jn_image,*tokenargs],1).decode()!='job/signer-changed\n':
                raise ValueError('actual job entry did not read synthetic token and derive signer')
            shortargs=list(jnargs); shortargs[6]='/case/short-key'
            if run([jn_image,*shortargs],1).decode()!='job run/bad-key\n':
                raise ValueError('actual job entry did not reject short key')
            (case/'source').write_text('tampered source')
            if run([realplan_image,*realargs],2).decode()!='consume/source-cid\n':
                raise ValueError('tampered source was not rejected')
            if marker.exists() or (case/'dispatched').exists(): raise ValueError('tampered source caused effects')
            (case/'source').write_text('bounded source')
            if run([realplan_image,*realargs])!=b'': raise ValueError('actual schedule path did not reach stub')
            if (case/'dispatched').read_text()!='called': raise ValueError('real-plan job stub not called')
            actual_cursor=(case/'cursor').read_bytes()
            actual_cid='b'+base64.b32encode(b'\x01\x55\x12\x20'+hashlib.sha256(actual_cursor).digest()).decode().lower().rstrip('=')
            actual_intent=('jti4\n'+pin+'\n'+actual_cid+'\n'+job+'\n1792638000000\n'+h('/case/cron.lock')+'\n'+
                           h('/case/token')+'\n'+h('ports')+'\n'+h('node-a')+'\n'+h('did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp')+'\n')
            if marker.read_text()!=actual_intent: raise ValueError('actual-plan marker binding mismatch')
            (case/'dispatched').write_text('existing')
            if run([realplan_image,*realargs],1).decode()!='cron-guard/turn-intent-unknown\n':
                raise ValueError('actual-plan duplicate was not refused')
            if (case/'dispatched').read_text()!='existing': raise ValueError('actual-plan job ran twice')
            if a.artifact_dir:
                a.artifact_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
                pins={}
                for name,image_path in [('fs2keyprobe',fs2key_image),('didprobe',did_image)]:
                    target=a.artifact_dir/(name+'.macho'); shutil.copyfile(image_path,target); target.chmod(0o700)
                    pins[name]=helper.digest(target.read_bytes())
                    if pins[name]!=helper.digest(image_path.read_bytes()): raise ValueError('artifact copy mismatch')
                manifest={'unitySha256':a.unity_sha256,'compilerSha256':a.compiler_sha256,
                          'packagerSha256':a.packager_sha256,'images':pins}
                manifest_path=a.artifact_dir/'manifest.json'
                manifest_path.write_text(json.dumps(manifest,sort_keys=True)+'\n')
                print('artifactManifestSha256',helper.digest(manifest_path.read_bytes()),flush=True)
            print(json.dumps({'unitySha256':a.unity_sha256,'fixtureSha256':helper.digest(source.encode()),
                              'positiveFixtureSha256':helper.digest(positive.encode()),
                              'actualPlanFixtureSha256':helper.digest(realplan.encode()),
                              'unframedKeyProbeSha256':helper.digest(keyprobe.encode()),
                              'fs2KeyProbeSha256':helper.digest(fs2keyprobe.encode()),
                              'didProbeSha256':helper.digest(didprobe.encode()),
                              'jobKeyProbeSha256':helper.digest(jnprobe.encode()),
                              'guardSourceSha256':helper.digest(current.encode()),'compilerSha256':a.compiler_sha256,
                              'packagerSha256':a.packager_sha256,'busyAndFourMarkersRefused':True,
                              'invalidPlanRefused':True,'turnGuardRemovalDetected':True,'jobStubNotReached':True,
                              'stubbedPositiveMarkerBeforeJob':True,'duplicateTurnRefused':True,
                              'actualPlanAndConsumeValidated':True,'tamperedSourceRefused':True,
                              'unframedKeyReadDiagnosticSigtrap':True,
                              'syntheticTokenAndJobSignerRefusalValidated':True,
                              'tokenShortReadMetadataAndChangeRefused':True,'tokenLengthGuardMutantAccepted':True,
                              'boundedKeyAndSignerValidated':True,
                              'jobEntryKeyAndSignerRefusalValidated':True,
                              'injectedMetadataAndShortFrameRefused':True,'metadataGuardMutantAccepted':True,
                              'scope':'native guard, diagnostic FS2 and flock; clock/job stubs; no production qualification'}))
        finally:
            if fd!=3:
                if saved is None: os.close(3)
                else: os.dup2(saved,3); os.close(saved)
            os.close(fd)


if __name__=='__main__': main()
