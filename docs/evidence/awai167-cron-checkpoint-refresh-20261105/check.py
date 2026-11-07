import hashlib, importlib.util, os, re, resource, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode=True
base=Path('/private/tmp/awai167-current-refresh-20261104.kotoba').read_text()
if hashlib.sha256(base.encode()).hexdigest()!='05c50d38bb0e6c92981d942443008eb8a56a2d84ebf045e54b9030c1c30a1cc9':raise RuntimeError('historical unity pin')
ito=Path('/Users/junkawasaki/github/workspaces/codex/awai147-job-archive-cursor');mura=Path('/Users/junkawasaki/github/workspaces/codex/awai150-verified-cron-input')
spec=importlib.util.spec_from_file_location('f',ito/'scripts/native/check-cron-decisions.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
paths=[(mura,'kotoba/'+p+'.kotoba') for p in ('git_checkpoint','fleet_job_output','fleet_job_output_archive','github_checkpoint_archive','github_checkpoint_head','github_checkpoint_head_graphql','fleet_job_node','fleet_cell_run','fleet_lease_node')]+[(ito,'kotoba/itonami/'+p+'.kotoba') for p in ('gateway_cursor','gateway_guarded_job_node','gateway_job_archive_cursor')]+[(ito,'test/native/'+p+'.kotoba') for p in ('gateway_cursor_cases','gateway_guarded_job_node_cases','gateway_job_archive_cursor_cases')]
selected={'kotoba/fleet_cell_run.kotoba': {'cr-key-meta','cr-key-digits?','cr-read-fs2-key','key-seed-fs2'}, 'kotoba/fleet_lease_node.kotoba': {'ln-frame','ln-fs','ln-exists?','lease-token-bounded'}}
names=set()
for root,path in paths:
 source=(root/path).read_text()
 for name in re.findall(r'^\(defn-?\s+([^\s\[]+)',source,re.M):
  if path in selected and name not in selected[path]:continue
  if name in names:raise RuntimeError('duplicate '+name)
  names.add(name);a,b=h.form(source,name);current=source[a:b]
  try:a,b=h.form(base,name);base=base[:a]+current+base[b:]
  except ValueError as e:
   if 'missing or duplicate' not in str(e):raise
   base+='\n'+current+'\n'
for root,path in paths:
 source=(root/path).read_text()
 for name in re.findall(r'^\(defn-?\s+([^\s\[]+)',source,re.M):
  if path in selected and name not in selected[path]:continue
  a,b=h.form(source,name);c,d=h.form(base,name)
  if source[a:b]!=base[c:d]:raise RuntimeError('mismatch '+name)
compiler=Path('/tmp/codex-amu-1762/seed/bootstrap/aarch64-macos/amu-full-root.macho');pin='920954769b8fdc51cf50dfcab5c44a4e56cf01f261806a153b21488ba81ac4e6'
if hashlib.sha256(compiler.read_bytes()).hexdigest()!=pin:raise RuntimeError('compiler pin')
with tempfile.TemporaryDirectory(prefix='awai167-composition-',dir='/private/tmp') as d:
 root=Path(d);(root/'unity.kotoba').write_text(base);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
 if fd!=3:os.dup2(fd,3)
 p=subprocess.run([str(compiler),'check','unity.kotoba'],cwd=root,pass_fds=(3,),env={'PATH':'/nonexistent'},capture_output=True,timeout=12,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CPU,(3,3)))
 if p.returncode or p.stderr:raise RuntimeError((p.returncode,p.stdout[-1000:],p.stderr[-1000:]))
 print('CHECK',p.stdout.decode().strip(),'functions',len(names),'sha256',hashlib.sha256(base.encode()).hexdigest(),flush=True)
 pack=Path('/private/tmp/awai154-fs2-darwin-gate/candidate.macho');pack_pin='f726f9dd8a4f169187275797a74d55ad3c62cc5f681cd31f19e1a28d67834f8d'
 if hashlib.sha256(pack.read_bytes()).hexdigest()!=pack_pin:raise RuntimeError('packager pin')
 import shutil
 a,b=h.form(base,'main');fixture=base[:a]+'(defn main [] :i64 (if (and (test-cron-cursor) (test-guarded-cron-cursor) (test-job-archive-cursor)) 0 1))'+base[b:]
 a,b=h.form(fixture,'cjg-cursor-problem');guard=fixture[a:b];needle='(not (= pending "0"))'
 if guard.count(needle)!=1:raise RuntimeError('mutant anchor')
 mutant=fixture[:a]+guard.replace(needle,'false')+fixture[b:]
 def run(args,expected=0):
  x=subprocess.run([str(z) for z in args],cwd=root,pass_fds=(3,),env={'PATH':'/nonexistent'},capture_output=True,timeout=12,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CPU,(3,3)))
  if x.returncode!=expected or x.stderr:raise RuntimeError((args,x.returncode,x.stdout[-500:],x.stderr[-500:]))
  return x.stdout
 def build(name,text):
  (root/(name+'.kotoba')).write_text(text);run([compiler,'compile',name+'.kotoba','--target','aarch64-macos','--output',name+'.kseed']);out=run([compiler,'extract-native',name+'.kseed','--symbol','main','--output',name+'.raw']);match=re.search(rb':offset (\d+), :length (\d+), :arity 0}',out)
  if not match or int(match[2])!=(root/(name+'.raw')).stat().st_size:raise RuntimeError('extract')
  run([pack,name+'-unsigned.macho',name+'.raw','fs2-cli-stdio-general',match[1].decode()]);img=root/(name+'.macho');shutil.copyfile(root/(name+'-unsigned.macho'),img);img.chmod(0o700);subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(img)],check=True,capture_output=True);return img
 run([build('cases',fixture)]);run([build('mutant',mutant)],1)
 print('PASS current cron decision cases and pending mutant',hashlib.sha256(fixture.encode()).hexdigest(),flush=True)
 os.close(3)
 if fd!=3:os.close(fd)
