"""Invoke reviewed hatchling metadata build while refusing upstream Python execution."""
from pathlib import Path
import hashlib,json,sys,runpy,os
root=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]);events=[]

def audit(event,args):
 if event=='exec':
  filename=getattr(args[0],'co_filename','')
  if filename and filename[0]!='<':
   p=Path(filename).resolve()
   if p==root or root in p.parents:
    events.append({'event':'refused_upstream_exec','relative_path':str(p.relative_to(root))})
    raise RuntimeError('build must not execute upstream source')
 if event=='import' and args[0].split('.')[0] in {'platformdirs','tests'}:
  events.append({'event':'refused_upstream_import','name':args[0]})
  raise RuntimeError('build must not import upstream source')
sys.addaudithook(audit);sys.dont_write_bytecode=True;os.chdir(root);sys.argv=['hatchling','build','-t','wheel'];code=0
try:runpy.run_module('hatchling',run_name='__main__')
except SystemExit as x:code=x.code or 0
finally:
 loaded=[n for n in sys.modules if n.split('.')[0] in {'platformdirs','tests'}]
 output.write_text(json.dumps({'exit_code':code,'refused_events':events,'upstream_modules_loaded':loaded,'source_root_execution_refused':True},indent=2)+'\n')
if code or events or loaded:raise SystemExit(code or 90)
