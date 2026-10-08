import copy,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reliability import DEFAULTS,validate,Cooling,button_action,atomic_save
from storage import DiskMonitor
class PolicyTests(unittest.TestCase):
 def setUp(self): self.c=copy.deepcopy(DEFAULTS); self.c['fall_delay']=0
 def test_emergency_overrides_off_and_test(self):
  self.c['mode']='off'
  for cpu in (80,100,None): self.assertEqual(Cooling().target(self.c,cpu,[],100,override=0)[0],100)
 def test_hot_active_disk_overrides_manual(self):
  self.c['mode']='manual'; self.c['manual_speed']=0
  d={'power':'Active','temperature':60,'sample_mono':100}
  self.assertEqual(Cooling().target(self.c,40,[d],100,override=0)[0],100)
 def test_standby_cache_cannot_trigger_emergency(self):
  d={'power':'Standby','temperature':None,'last_temperature':90,'sample_mono':0}
  self.assertEqual(Cooling().target(self.c,40,[d],1000)[0],0)
 def test_unknown_disk_enforces_minimum(self):
  self.assertEqual(Cooling().target(self.c,40,[{'power':'Unknown'}],1000)[0],40)
 def test_stale_active_disk_enforces_minimum(self):
  self.assertEqual(Cooling().target(self.c,40,[{'power':'Active','temperature':30,'sample_mono':0}],1000)[0],40)
 def test_decline_delayed_rise_immediate(self):
  self.c['fall_delay']=30;p=Cooling()
  self.assertEqual(p.target(self.c,40,[],100)[0],100)
  self.assertEqual(p.target(self.c,40,[],129)[0],100)
  self.assertEqual(p.target(self.c,40,[],131)[0],0)
  self.assertEqual(p.target(self.c,80,[],132)[0],100)
 def test_validation_rejects_invalid_curves(self):
  for curve in ([],[[50,90],[40,100]],[[40,90],[50,20]],[[40,float('nan')]],[[40,200]]):
   with self.assertRaises(ValueError):validate({'cpu_curve':curve})
 def test_invalid_safety_is_rejected(self):
  for values in ({'mode':'bad'},{'brightness':0},{'emergency_cpu':100},{'button_actions':'false'},{'drive_types':{'sda;reboot':'sat'}}):
   with self.assertRaises(ValueError):validate(values)
 def test_atomic_valid_json(self):
  p=Path(tempfile.mkdtemp())/'settings.json';atomic_save(p,DEFAULTS);self.assertEqual(json.loads(p.read_text()),DEFAULTS)
 def test_button_noise_ignored(self):
  for ms in (0,1,14,76,100,3000): self.assertIsNone(button_action(ms))
  self.assertEqual(button_action(25),'reboot');self.assertEqual(button_action(45),'shutdown');self.assertEqual(button_action(65),'page')
class StorageTests(unittest.TestCase):
 row={'name':'sda','identity':'port1','model':'test','device':'/dev/sda','temperature':None,'power':'Unknown'}
 standby={'smartctl':{'messages':[{'string':'Device is in STANDBY mode, exit(99)'}]}}
 def run_fake(self,code,data):
  def run(cmd,**kw):
   self.commands.append(cmd)
   class R: pass
   r=R();r.returncode=code;r.stdout=json.dumps(data);return r
  return run
 def setUp(self):self.commands=[]
 def test_no_type_means_no_probe(self):
  m=DiskMonitor(self.run_fake(0,{}));m.poll({},[self.row]);self.assertEqual(self.commands,[])
 def test_standby_single_nonwaking_command(self):
  m=DiskMonitor(self.run_fake(99,self.standby));d=m.poll({'sda':'sat'},[self.row])[0]
  self.assertEqual(d['power'],'Standby');self.assertEqual(len(self.commands),1)
  self.assertIn('standby,99,98',self.commands[0]);self.assertIn('sat',self.commands[0]);self.assertNotIn('auto',self.commands[0])
 def test_unsupported_no_fallback(self):
  m=DiskMonitor(self.run_fake(98,{}));d=m.poll({'sda':'sat'},[self.row])[0];self.assertEqual(d['power'],'Unknown');self.assertEqual(len(self.commands),1)
 def test_cache_preserved_standby(self):
  m=DiskMonitor(self.run_fake(0,{'temperature':{'current':43},'smart_status':{'passed':True}}));m.poll({'sda':'sat'},[self.row]);m.run=self.run_fake(99,self.standby)
  d=m.poll({'sda':'sat'},[self.row])[0];self.assertEqual(d['last_temperature'],43);self.assertIsNone(d['temperature']);self.assertIsNotNone(d['last_measured'])
 def test_false_pass_not_assumed(self):
  m=DiskMonitor(self.run_fake(0,{}));self.assertEqual(m.poll({'sda':'sat'},[self.row])[0]['health'],'Unknown')
 def test_test_defers_sleeping(self):
  m=DiskMonitor(self.run_fake(99,{}));self.assertEqual(m.test('sda','sat','long')['status'],'deferred')
if __name__=='__main__': unittest.main()
