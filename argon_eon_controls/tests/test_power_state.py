import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reliability import DEFAULTS,Cooling
from storage import DiskMonitor,power_mode
def exit99(mode):
 return {'smartctl':{'messages':[{'string':'Device is in %s mode, exit(99)'%mode}]}}
class PowerStateTests(unittest.TestCase):
 row={'name':'sda','identity':'port1','model':'test','device':'/dev/sda','temperature':None,'power':'Unknown'}
 def poll(self,data,code=99):
  def run(cmd,**kw):
   class R: pass
   r=R();r.returncode=code;r.stdout=json.dumps(data);return r
  return DiskMonitor(run).poll({'sda':'sat'},[self.row])[0]
 def test_standby_is_standby(self):
  for mode in ('STANDBY','STANDBY_Y'): self.assertEqual(self.poll(exit99(mode))['power'],'Standby')
 def test_failed_power_check_is_not_standby(self):
  d=self.poll(exit99('SLEEP'));self.assertEqual(d['power'],'Unknown');self.assertIn('failed',d['message'])
 def test_missing_message_is_not_standby(self):
  self.assertEqual(self.poll({})['power'],'Unknown')
 def test_unknown_power_keeps_minimum_fan_but_standby_does_not(self):
  c=copy.deepcopy(DEFAULTS);c['fall_delay']=0
  self.assertEqual(Cooling().target(c,40,[self.poll(exit99('SLEEP'))],1000)[0],40)
  self.assertEqual(Cooling().target(c,40,[self.poll(exit99('STANDBY'))],1000)[0],0)
 def test_power_mode_parse(self):
  self.assertEqual(power_mode(exit99('STANDBY_Y')),'STANDBY_Y');self.assertIsNone(power_mode({}))
if __name__=='__main__':unittest.main()
