"""Validated configuration and pure cooling policy; no device access."""
import copy, json, math, os
from pathlib import Path
DEFAULTS = dict(mode='auto', manual_speed=40, poll_seconds=10, fall_delay=30,
 cpu_curve=[[45,0],[52,25],[58,40],[64,60],[72,100]],
 disk_curve=[[35,0],[40,25],[44,40],[48,60],[55,100]],
 emergency_cpu=80, emergency_disk=55, failsafe_speed=100,
 missing_temp_grace=0, minimum_unmonitored=40, screensaver_seconds=0, auto_i2c=True,
 oled_enabled=True, oled_pages=['clock','temperature','storage','network'],
 page_seconds=15, brightness=60, burnin_enabled=True,
 burnin_rest_minutes=30,burnin_rest_seconds=60,night_start='23:00',night_end='07:00',
 night_enabled=False, timezone='Europe/London', custom_line_1='Home Assistant',
 custom_line_2='Storage online',publish_entities=True,notifications=True,
 button_actions=False,button_reboot=False,drive_types={},
 smart_schedule='disabled',smart_test='short')
PAGES = {'clock','temperature','storage','network','custom','cpu','ram','bandwidth','raid','alerts','cooling','uptime'}

def validate(data):
 if not isinstance(data,dict): raise ValueError('Settings must be an object')
 if set(data)-set(DEFAULTS): raise ValueError('Unknown settings: '+', '.join(set(data)-set(DEFAULTS)))
 c=copy.deepcopy(DEFAULTS); c.update(data)
 for key, default in DEFAULTS.items():
  if isinstance(default,bool) and type(c[key]) is not bool: raise ValueError(key+' must be true/false')
 for key,lo,hi in [('manual_speed',0,100),('fall_delay',0,120),('emergency_cpu',65,80),('emergency_disk',45,60),('minimum_unmonitored',0,100),('screensaver_seconds',0,3600),('page_seconds',3,3600),('brightness',10,100),('burnin_rest_minutes',5,1440),('burnin_rest_seconds',10,300)]:
  if type(c[key]) not in (int,float) or not math.isfinite(c[key]) or not lo<=c[key]<=hi: raise ValueError(f'{key} must be {lo}–{hi}')
  c[key]=int(c[key])
 c['poll_seconds']=10; c['failsafe_speed']=100; c['missing_temp_grace']=0
 if c['mode'] not in ('auto','manual','off'): raise ValueError('Invalid fan mode')
 for key in ('cpu_curve','disk_curve'):
  points=c[key]
  if not isinstance(points,list) or not 1<=len(points)<=12: raise ValueError('Use 1–12 fan curve points')
  previous=(-1,-1)
  for p in points:
   if not isinstance(p,list) or len(p)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) for n in p): raise ValueError('Invalid curve point')
   t,s=p
   if not 0<=t<=90 or not 0<=s<=100 or int(s)!=s or t<=previous[0] or s<previous[1]: raise ValueError('Temperatures must increase; fan speeds cannot decrease')
   previous=(t,s)
 if not isinstance(c['oled_pages'],list) or not c['oled_pages'] or len(c['oled_pages'])!=len(set(c['oled_pages'])) or set(c['oled_pages'])-PAGES: raise ValueError('Select distinct display pages')
 for k in ('custom_line_1','custom_line_2'):
  if not isinstance(c[k],str) or len(c[k])>21: raise ValueError('Custom text maximum 21 characters')
 from zoneinfo import ZoneInfo
 ZoneInfo(c['timezone'])
 import re
 for k in ('night_start','night_end'):
  if not isinstance(c[k],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',c[k]): raise ValueError('Time must be HH:MM')
 if c['smart_schedule'] not in ('disabled','weekly','monthly') or c['smart_test'] not in ('short','long'): raise ValueError('Invalid SMART schedule')
 if not isinstance(c['drive_types'],dict): raise ValueError('drive_types must be a mapping')
 for name,kind in c['drive_types'].items():
  if not re.fullmatch(r'sd[a-z]+',name) or kind not in ('sat','sat,12','sat,16','ignore'): raise ValueError('Only explicit SATA bridge types supported')
 return c

def atomic_save(path,data):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp')
 with tmp.open('w') as f:
  json.dump(data,f,indent=2,allow_nan=False); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try: os.fsync(fd)
 finally: os.close(fd)

def curve(temp,points):
 return max([s for t,s in points if temp is not None and temp>=t]+[0])

class Cooling:
 def __init__(self): self.last=100; self.down_since=None
 def target(self,c,cpu,drives,now,override=None,commissioned=True):
  live=[(d.get('name','?'),d['temperature']) for d in drives if d.get('power')=='Active' and d.get('temperature') is not None and now-d.get('sample_mono',0)<=320]
  fresh=[t for _,t in live]
  emergency=cpu is not None and cpu>=c['emergency_cpu'] or any(t>=c['emergency_disk'] for t in fresh)
  if cpu is None or emergency or not commissioned:
   self.last=100; self.down_since=None
   return 100,'Emergency temperature' if emergency else 'CPU unavailable or commissioning pending'
  wanted,why=max([(curve(cpu,c['cpu_curve']),'CPU %.0f°C'%cpu)]+[(curve(t,c['disk_curve']),'Disk %s %.0f°C'%(n,t)) for n,t in live],key=lambda x:x[0])
  if c['mode']=='manual': wanted,why=c['manual_speed'],'Manual mode'
  if c['mode']=='off': wanted,why=0,'Fan mode is off'
  if override is not None: wanted,why=override,'Temporary fan test'
  blind=[d.get('name','?') for d in drives if d.get('power') not in ('Standby','No media','Ignored') and (d.get('temperature') is None or now-d.get('sample_mono',0)>320)]
  if blind and c['minimum_unmonitored']>wanted: wanted,why=c['minimum_unmonitored'],'Minimum %d%%: cannot read temperature of %s'%(c['minimum_unmonitored'],', '.join(blind))
  if wanted<self.last and override is None:
   if self.down_since is None: self.down_since=now
   if now-self.down_since<c['fall_delay']: return self.last,'Cooling down: delay (%s wants %d%%)'%(why,wanted)
  else: self.down_since=None
  self.last=wanted; self.down_since=None  # every reduction earns its own delay
  return wanted,why

def button_action(milliseconds):
 # Upstream encodes actions in ~20/40/60 ms pulses, not the user's hold duration.
 if 15<=milliseconds<=35: return 'reboot'
 if 35<milliseconds<=55: return 'shutdown'
 if 55<milliseconds<=75: return 'page'
 return None
