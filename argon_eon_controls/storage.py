"""No disk reads for inventory. SMART uses explicit bridge type and fail-closed -n."""
import json, re, subprocess, time
from pathlib import Path

def stable_identity(resolved_path):
 """A device identity that survives the kernel renaming a drive (sda -> sdb etc. across a reconnect
 or reboot): the USB port-chain portion of the sysfs path, which is tied to the physical port rather
 than the transient device letter. Falls back to the full resolved path for any other topology."""
 m=re.search(r'(.*/\d+-\d+(?:\.\d+)*:[\d.]+)/',resolved_path)
 base=m.group(1) if m else resolved_path
 # Disks sharing one USB bridge (EON bays) are told apart by SCSI channel:target:lun; LUN 0 keeps the old identity.
 s=re.search(r'/host\d+/target\d+:\d+:\d+/\d+:(\d+):(\d+):(\d+)(?:/|$)',resolved_path)
 return base+'#'+':'.join(s.groups()) if m and s and s.groups()!=('0','0','0') else base

CARRIED=('serial_tail','model_name','reallocated','pending','uncorrectable','power_on_hours')   # kept from the last awake reading while a drive sleeps

def eon_bridge_type(base):
 """Argon EON bays sit behind USB-SATA bridges (174e:1155 UAS, 1741:1156) that answer SAT passthrough, so
 they get the explicit 'sat' type by default. Detection reads the USB IDs from sysfs (no disk access).
 Anything else (e.g. a drive on the Pi's own USB port) is left unmonitored until the user picks a type."""
 ident=(base.get('identity') or '').split('#')[0]
 if not ident: return None
 try:
  usb=Path(ident).parent
  ids=((usb/'idVendor').read_text().strip().lower(),(usb/'idProduct').read_text().strip().lower())
 except (OSError,ValueError): return None
 return 'sat' if ids in (('174e','1155'),('1741','1156')) else None

def inventory():
 result=[]
 for p in sorted(Path('/sys/block').glob('sd*')):
  def read(s,default=''):
   try: return (p/s).read_text().strip()
   except OSError: return default
  resolved=str(p.resolve())
  result.append(dict(name=p.name,device='/dev/'+p.name,model=read('device/model'),
   size=int(read('size','0'))*512,rotational=read('queue/rotational')=='1',
   discard_max_bytes=int(read('queue/discard_max_bytes','0')),
   identity=stable_identity(resolved),power='Unknown',temperature=None))
 return result

def power_mode(data):
 """Power-mode name smartctl printed when it exited early ('STANDBY', 'SLEEP', ...), else None."""
 text=' '.join(str(m.get('string','')) for m in data.get('smartctl',{}).get('messages',[]))
 found=re.search(r'Device is in (\w+) mode',text)
 return found.group(1) if found else None

class DiskMonitor:
 def __init__(self,run=subprocess.run): self.run=run; self.cache={}
 def smart(self,name,kind,args):
  # 99 = asleep, 98 = power-mode check unsupported. Explicit -d avoids waking autodetection.
  cmd=['smartctl','-j','-d',kind,'-n','standby,99,98',*args,'/dev/'+name]
  r=self.run(cmd,capture_output=True,text=True,timeout=8)
  try: data=json.loads(r.stdout or '{}')
  except ValueError: data={}
  return r.returncode,data
 def poll(self,types,rows=None):
  rows=inventory() if rows is None else rows; output=[]
  for base in rows:
   name=base['name']; previous=self.cache.get(base.get('identity'),{})
   d=dict(base,last_temperature=previous.get('last_temperature'),last_measured=previous.get('last_measured'),health='Unknown')
   kind=types.get(name); auto=False
   if not kind: kind=eon_bridge_type(base); auto=bool(kind)
   d.update(bridge_type=kind,bridge_auto=auto)
   if base.get('size')==0: d.update(power='No media',message='No media in this bay; not monitored')
   elif kind=='ignore': d.update(power='Ignored',message='Ignored by setting (not monitored, not polled)')
   elif not kind:
    d['message']='Select verified SATA bridge type; SMART probing disabled'
   else:
    try:
     code,data=self.smart(name,kind,['-a'])
     if code==99:
      # smartctl also exits 99 ("SLEEP") when CHECK POWER MODE itself failed; only STANDBY proves a sleeping disk.
      if power_mode(data) in ('STANDBY','STANDBY_Y'): d.update(power='Standby',health=previous.get('health','Unknown')); d.update({k:previous[k] for k in CARRIED if previous.get(k) is not None})
      else: d['message']='Power-mode check failed (smartctl reported '+str(power_mode(data))+'); treated as unmonitored'
     elif code==98: d['message']='Power check unsupported; no further SMART commands sent'
     elif code & 3:
      why=next((str(m.get('string','')) for m in data.get('smartctl',{}).get('messages',[]) if m.get('severity')=='error'),'') or next((str(m.get('string','')) for m in data.get('smartctl',{}).get('messages',[])),'')
      d['message']='SMART command failed (exit %d): %s. Bridge type %s; no fallback probing'%(code,why or 'no message',kind)
     else:
      temp=data.get('temperature',{}).get('current')
      attrs={a['id']:a.get('raw',{}).get('value') for a in data.get('ata_smart_attributes',{}).get('table',[])}
      if temp is None: temp=attrs.get(194,attrs.get(190))
      if type(temp) not in (int,float) or not 0<=temp<=100: temp=None
      passed=data.get('smart_status',{}).get('passed')
      counts={k:v for k,v in (('pending',attrs.get(197)),('uncorrectable',attrs.get(198))) if type(v) is int and v>0}
      reasons=(['overall SMART status FAILED'] if passed is False or code&8 else [])+(['pre-failure attribute at/below threshold'] if code&16 else [])+['%d %s sectors'%(v,k) for k,v in counts.items()]
      notes=[t for bit,t in ((32,'attribute was at/below threshold in the past'),(64,'error log has entries'),(128,'self-test log has errors')) if code&bit]
      d.update(power='Active',temperature=temp,health='Failed' if passed is False or code&(8|16) else 'Warning' if counts else 'Passed' if passed is True else 'Unknown',
       message='; '.join(reasons) or None,smart_notes=notes,serial_tail=str(data.get('serial_number') or '')[-4:] or None,model_name=data.get('model_name'),
       reallocated=attrs.get(5),pending=attrs.get(197),uncorrectable=attrs.get(198),
       power_on_hours=data.get('power_on_time',{}).get('hours'),smart_exit=code,
       self_test=data.get('ata_smart_self_test_log',{}))
      if temp is not None: d.update(last_temperature=temp,last_measured=time.time(),sample_mono=time.monotonic())
    except (subprocess.TimeoutExpired,OSError) as e: d['message']=type(e).__name__
   output.append(d)
  self.cache={d['identity']:d for d in output if d.get('identity')}
  return output
 def test(self,name,kind,test):
  if test not in ('short','long'): raise ValueError('Invalid test')
  # Even explicitly requested tests defer while asleep; no wake-up command exists here.
  code,data=self.smart(name,kind,['-t',test])
  if code in (98,99): return {'status':'deferred','reason':'Standby or unsupported power check'}
  if code&7: raise RuntimeError('SMART test rejected: '+str(code))
  return {'status':'requested','details':data.get('smartctl',{}).get('messages',[])}

def _who(d):
 import re
 port=re.findall(r'/(\d+-\d+(?:\.\d+)*):',d.get('identity') or '')
 extra=(['%.0f GB'%(d['size']/1e9)] if d.get('size') else [])+(['S/N ...'+d['serial_tail']] if d.get('serial_tail') else [])+(['USB port '+port[-1]] if port else [])
 return ' '.join(x for x in (d['name'],d.get('model')) if x)+(' ('+', '.join(extra)+')' if extra else '')

def smart_event(d,alerted):
 """Message for a serious SMART state: once per drive per escalation, re-armed only when that drive reports Passed.
 Sleeping drives keep their last health, so they never repeat an alert."""
 key=d.get('identity'); health=d.get('health')
 if health=='Passed': alerted.pop(key,None)
 elif health in ('Failed','Warning') and alerted.get(key)!=health and not (health=='Warning' and alerted.get(key)=='Failed'):
  alerted[key]=health
  return 'SMART '+('health failed' if health=='Failed' else 'warning')+': '+_who(d)+' - '+(d.get('message') or 'see dashboard')
 return None
