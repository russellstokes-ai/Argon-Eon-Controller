"""Home Assistant entities for the monitored drives. Pure functions: no I/O, tested without Home Assistant."""
import re
from datetime import datetime,timezone

def slug(text):
 return re.sub(r'[^a-z0-9]+','_',str(text).lower()).strip('_') or 'unknown'

def monitored(d):
 """A drive worth reporting on: not ignored, not an empty bay, and with a SMART type (chosen or automatic)."""
 return d.get('power') not in ('Ignored','No media') and d.get('bridge_type') not in (None,'','ignore')

def _keys(disks):
 """One stable key per drive. The serial tail follows the physical disk across reboots and device-letter changes,
 so its history is not mixed with another disk's; without one (never read yet) or on a clash, use the device name."""
 tails=[slug(d['serial_tail']) for d in disks if d.get('serial_tail')]
 out={}
 for d in disks:
  t=slug(d['serial_tail']) if d.get('serial_tail') else None
  out[d['name']]='drive_'+t if t and tails.count(t)==1 else slug(d['name'])
 return out

def _iso(epoch):
 try: return datetime.fromtimestamp(float(epoch),timezone.utc).isoformat(timespec='seconds')
 except (TypeError,ValueError,OverflowError,OSError): return None

def _temperature(d):
 cur=d.get('temperature'); last=d.get('last_temperature')
 return (cur if cur is not None else last),cur is None and last is not None

def drive_entities(disks):
 """[(entity_id, state, attributes)] for every monitored drive, plus a hottest-drive sensor and a problem flag."""
 mon=[d for d in disks if monitored(d)]; keys=_keys(mon); out=[]; temps=[]; bad=[]
 for d in mon:
  k=keys[d['name']]; label=d.get('model_name') or d['name']; tail=d.get('serial_tail')
  who=label+(' (…%s)'%tail if tail else '')
  val,cached=_temperature(d)
  if val is not None: temps.append(val)
  out.append(('sensor.argon_eon_%s_temperature'%k,val if val is not None else 'unavailable',{
   'friendly_name':'Argon EON %s temperature'%who,'unit_of_measurement':'°C','device_class':'temperature','state_class':'measurement',
   'device':d['name'],'model':label,'power':d.get('power'),'cached_reading':cached,'measured_at':_iso(d.get('last_measured'))}))
  health=d.get('health') or 'Unknown'
  if health in ('Warning','Failed'): bad.append('%s: %s'%(d['name'],health))
  out.append(('sensor.argon_eon_%s_health'%k,health,{
   'friendly_name':'Argon EON %s SMART health'%who,'icon':'mdi:harddisk' if health in ('Passed','Unknown') else 'mdi:harddisk-remove',
   'device':d['name'],'model':label,'power':d.get('power'),'reallocated_sectors':d.get('reallocated'),'pending_sectors':d.get('pending'),
   'uncorrectable_sectors':d.get('uncorrectable'),'power_on_hours':d.get('power_on_hours'),'detail':d.get('message')}))
 out.append(('sensor.argon_eon_hottest_drive_temperature',max(temps) if temps else 'unavailable',{
  'friendly_name':'Argon EON hottest drive temperature','unit_of_measurement':'°C','device_class':'temperature','state_class':'measurement'}))
 out.append(('binary_sensor.argon_eon_drive_problem','on' if bad else 'off',{
  'friendly_name':'Argon EON drive problem','device_class':'problem','drives':bad}))
 return out
