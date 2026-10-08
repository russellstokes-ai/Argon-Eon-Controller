"""Free presence/activity watch. Reads only kernel counters under /sys/block:
no command of any kind is sent to a disk, so watching can never wake one."""
import re
from pathlib import Path
from storage import stable_identity

def snapshot(root='/sys/block'):
 result={}
 for p in sorted(Path(root).glob('sd*')):
  def read(rel):
   try: return (p/rel).read_text().strip()
   except OSError: return None
  f=(read('stat') or '').split()
  io=(int(f[0]),int(f[4])) if len(f)>=5 and f[0].isdigit() and f[4].isdigit() else None  # reads, writes completed
  identity=stable_identity(str(p.resolve()))
  result[identity]=dict(name=p.name,vendor=read('device/vendor'),model=read('device/model'),identity=identity,io=io,size=int(read('size') or 0)*512)
 return result

def port(identity):
 found=re.findall(r'/(\d+-\d+(?:\.\d+)*):',identity or '')
 return found[-1] if found else None

def describe(disk):
 model=' '.join(x for x in (disk.get('vendor'),disk.get('model')) if x)
 extra=[]
 if disk.get('size'): extra.append('%.0f GB'%(disk['size']/1e9))
 if port(disk.get('identity')): extra.append('USB port '+port(disk['identity']))
 return ' '.join(x for x in (disk['name'],model) if x)+(' ('+', '.join(extra)+')' if extra else '')

def disappeared(previous,current): return sorted(set(previous)-set(current))
def appeared(previous,current): return sorted(set(current)-set(previous))
def woken(previous,current):
 """Disks whose completed-I/O counters moved: the OS touched them, so they may have spun up."""
 return sorted(n for n in set(previous)&set(current) if previous[n]['io'] is not None and current[n]['io'] is not None and previous[n]['io']!=current[n]['io'])
