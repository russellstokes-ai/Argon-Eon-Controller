import os,sys,tempfile,unittest
from pathlib import Path
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from entities import drive_entities,monitored,slug,_keys
from storage import DiskMonitor

def disk(name,**kw):
 d=dict(name=name,power='Active',health='Passed',bridge_type='sat',temperature=33,last_temperature=33,last_measured=1791121000.,
        serial_tail='A1B2',model_name='Samsung SSD 850 PRO 1TB',pending=0,reallocated=0,uncorrectable=0,power_on_hours=100,message=None)
 d.update(kw); return d
FLEET=[disk('sda',bridge_type=None,power='Unknown',health='Unknown',temperature=None,last_temperature=None,serial_tail=None,model_name=None),
       disk('sdb',power='No media',health='Unknown',temperature=None,last_temperature=None,serial_tail=None,model_name=None),
       disk('sdc',health='Warning',temperature=34,serial_tail='ZZ09',model_name='ST1000LM035-1RK172',pending=2944,message='2944 pending sectors'),
       disk('sdd')]
def by_id(rows): return {e:(s,a) for e,s,a in rows}

class DriveEntities(unittest.TestCase):
 def test_only_monitored_drives_get_sensors(self):
  ids=by_id(drive_entities(FLEET))
  self.assertEqual(sorted(k for k in ids if k.endswith(('_temperature','_health')) and 'hottest' not in k),
   ['sensor.argon_eon_drive_a1b2_health','sensor.argon_eon_drive_a1b2_temperature','sensor.argon_eon_drive_zz09_health','sensor.argon_eon_drive_zz09_temperature'])
  self.assertFalse([k for k in ids if 'sda' in k or 'sdb' in k])      # unmonitored drive and empty bay: nothing published
 def test_values_and_attributes(self):
  ids=by_id(drive_entities(FLEET)); s,a=ids['sensor.argon_eon_drive_zz09_temperature']
  self.assertEqual(s,34); self.assertEqual((a['unit_of_measurement'],a['device_class'],a['state_class']),('°C','temperature','measurement'))
  self.assertEqual((a['device'],a['model'],a['cached_reading']),('sdc','ST1000LM035-1RK172',False)); self.assertTrue(a['measured_at'].startswith('2026-'))
  s,a=ids['sensor.argon_eon_drive_zz09_health']
  self.assertEqual((s,a['pending_sectors'],a['power_on_hours'],a['icon']),('Warning',2944,100,'mdi:harddisk-remove'))
  self.assertIn('ST1000LM035-1RK172',a['friendly_name']); self.assertIn('ZZ09',a['friendly_name'])
 def test_hottest_and_problem_sensors(self):
  ids=by_id(drive_entities(FLEET))
  self.assertEqual(ids['sensor.argon_eon_hottest_drive_temperature'][0],34)
  s,a=ids['binary_sensor.argon_eon_drive_problem']; self.assertEqual((s,a['device_class'],a['drives']),('on',['problem'][0],['sdc: Warning']))
  healthy=by_id(drive_entities([disk('sdd')])); self.assertEqual(healthy['binary_sensor.argon_eon_drive_problem'][0],'off')
 def test_failed_also_raises_the_problem_flag(self):
  self.assertEqual(by_id(drive_entities([disk('sdc',health='Failed')]))['binary_sensor.argon_eon_drive_problem'][0],'on')
 def test_a_sleeping_drive_keeps_its_last_temperature_marked_as_cached(self):
  s,a=by_id(drive_entities([disk('sdc',power='Standby',temperature=None,last_temperature=31)]))['sensor.argon_eon_drive_a1b2_temperature']
  self.assertEqual((s,a['cached_reading'],a['power']),(31,True,'Standby'))
 def test_unreadable_temperature_is_unavailable_not_zero(self):
  rows=by_id(drive_entities([disk('sdc',temperature=None,last_temperature=None)]))
  self.assertEqual(rows['sensor.argon_eon_drive_a1b2_temperature'][0],'unavailable'); self.assertEqual(rows['sensor.argon_eon_hottest_drive_temperature'][0],'unavailable')
 def test_no_monitored_drives_still_reports_a_quiet_problem_sensor(self):
  rows=by_id(drive_entities([FLEET[0],FLEET[1]])); self.assertEqual(rows['binary_sensor.argon_eon_drive_problem'][0],'off'); self.assertEqual(len(rows),2)
 def test_ids_are_valid_home_assistant_ids(self):
  import re
  for e,_,_ in drive_entities(FLEET): self.assertRegex(e,r'^(sensor|binary_sensor)\.[a-z0-9_]+$')
 def test_key_follows_the_serial_not_the_device_letter(self):
  a=_keys([disk('sdc',serial_tail='ZZ09')]); b=_keys([disk('sdg',serial_tail='ZZ09')]); self.assertEqual(a['sdc'],b['sdg'])
 def test_duplicate_or_missing_serial_falls_back_to_the_device_name(self):
  k=_keys([disk('sdc',serial_tail='SAME'),disk('sdd',serial_tail='SAME'),disk('sde',serial_tail=None)])
  self.assertEqual((k['sdc'],k['sdd'],k['sde']),('sdc','sdd','sde'))
 def test_slug_and_monitored(self):
  self.assertEqual(slug('ST1000-LM 035!'),'st1000_lm_035'); self.assertEqual(slug(''),'unknown')
  self.assertFalse(monitored(disk('x',bridge_type='ignore'))); self.assertFalse(monitored(disk('x',power='Ignored'))); self.assertTrue(monitored(disk('x')))

class SleepingDriveKeepsItsIdentity(unittest.TestCase):
 def test_serial_model_and_counts_survive_a_standby_poll(self):
  prev={'identity':'/p','last_temperature':31,'last_measured':5.,'health':'Warning','serial_tail':'ZZ09','model_name':'ST1000LM035-1RK172','pending':2944,'reallocated':0,'uncorrectable':2944,'power_on_hours':3452}
  import json
  def run(cmd,**kw):
   class R: pass
   r=R(); r.returncode=99; r.stdout=json.dumps({'smartctl':{'messages':[{'string':'Device is in STANDBY mode, exit(99)'}]}}); return r
  m=DiskMonitor(run); m.cache={'/p':prev}
  d=m.poll({'sdc':'sat'},[{'name':'sdc','identity':'/p','model':'SATA','device':'/dev/sdc','size':1,'power':'Unknown','temperature':None}])[0]
  self.assertEqual(d['power'],'Standby'); self.assertEqual((d['serial_tail'],d['model_name'],d['pending'],d['uncorrectable'],d['health']),('ZZ09','ST1000LM035-1RK172',2944,2944,'Warning'))
 def test_real_model_name_is_recorded_when_awake(self):
  import json
  data={'model_name':'Samsung SSD 850 PRO 1TB','serial_number':'S2BBNXAG123456','temperature':{'current':30},'smart_status':{'passed':True},'ata_smart_attributes':{'table':[]}}
  def run(cmd,**kw):
   class R: pass
   r=R(); r.returncode=0; r.stdout=json.dumps(data); return r
  d=DiskMonitor(run).poll({'sdd':'sat'},[{'name':'sdd','identity':'/q','model':'SATA','device':'/dev/sdd','size':1,'power':'Unknown','temperature':None}])[0]
  self.assertEqual((d['model_name'],d['serial_tail']),('Samsung SSD 850 PRO 1TB','3456'))

if __name__=='__main__': unittest.main()

class TelemetryPublishesDriveSensors(unittest.TestCase):
 """End to end through the real telemetry loop with a fake Home Assistant: what is posted, retired, and what a failure does."""
 def run_loop(self,disks_by_iteration,fail_on=None,iterations=4,extra=None):
  import copy,app
  from unittest.mock import patch
  from reliability import DEFAULTS
  posts=[]; n=[0]
  def fake_supervisor(path,body=None):
   if fail_on and fail_on in path: raise RuntimeError('HA said no')
   posts.append((path,body)); return {'data':{}}
  def fake_wait(t=None):
   n[0]+=1
   with app.lock: app.state['disks']=disks_by_iteration[min(n[0],len(disks_by_iteration)-1)]
   if n[0]>=iterations: app.stop.set()
   return False
  app.stop.clear()
  with app.lock: saved=(app.cfg,app.state['disks'],app.state.get('ha_error')); app.cfg=copy.deepcopy(DEFAULTS); app.state['disks']=disks_by_iteration[0]; app.state.update(extra or {})
  try:
   with patch('app.supervisor',fake_supervisor),patch('app.STANDALONE',False),patch('app.usb_devices',return_value=[]),patch('app.metrics',return_value={}),\
        patch.object(app,'hw',type('H',(),{'rtc_status':lambda s:{}})()),patch.object(app.stop,'wait',fake_wait):
    app.telemetry()
   with app.lock: ha_error=app.state.get('ha_error')
  finally:
   app.stop.clear()
   with app.lock:
    app.cfg,app.state['disks']=saved[0],saved[1]; app.state['ha_error']=saved[2]
    for k in (extra or {}): app.state.pop(k,None)
  return posts,ha_error
 def test_drive_sensors_are_posted_with_their_attributes(self):
  posts,err=self.run_loop([FLEET],iterations=2); got={p.split('/states/')[1]:b for p,b in posts if '/states/' in p}
  self.assertIn('sensor.argon_eon_cpu_temperature',got)   # the existing sensors are still published
  self.assertEqual(got['sensor.argon_eon_drive_zz09_temperature']['state'],34)
  self.assertEqual(got['binary_sensor.argon_eon_drive_problem']['state'],'on'); self.assertIsNone(err)
 def test_a_drive_that_disappears_is_marked_unavailable_once(self):
  posts,_=self.run_loop([FLEET,FLEET,[FLEET[3]],[FLEET[3]]],iterations=4)
  gone=[b for p,b in posts if p.endswith('drive_zz09_temperature')]
  self.assertEqual([b['state'] for b in gone],[34,34,'unavailable'])    # no repeated 'unavailable' posts after that
 def test_a_failing_drive_sensor_is_reported_but_never_blocks_cpu_fan_sensors_or_notifications(self):
  posts,err=self.run_loop([FLEET],fail_on='drive_zz09',iterations=2,extra={'fan_error':'fan bus down'})
  self.assertEqual(err,'HA said no')                                                               # shown as the add-on's Home Assistant error
  self.assertTrue([p for p,_ in posts if p.endswith('sensor.argon_eon_cpu_temperature')])
  self.assertTrue([b for p,b in posts if p.endswith('persistent_notification/create') and 'fan bus down' in b['message']])   # notification still raised
