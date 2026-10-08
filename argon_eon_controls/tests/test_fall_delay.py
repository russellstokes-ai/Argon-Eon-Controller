import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reliability import DEFAULTS,Cooling
class FallDelayTests(unittest.TestCase):
 def test_each_step_down_waits_its_own_delay(self):
  c=copy.deepcopy(DEFAULTS);c['fall_delay']=30;p=Cooling()
  self.assertEqual(p.target(c,72,[],1000)[0],100)
  self.assertEqual(p.target(c,64,[],1010)[0],100)   # 60% wanted, held
  self.assertEqual(p.target(c,64,[],1039)[0],100)
  self.assertEqual(p.target(c,64,[],1041)[0],60)    # first step down after 30 s
  self.assertEqual(p.target(c,58,[],1050)[0],60)    # 40% wanted: must wait again
  self.assertEqual(p.target(c,58,[],1079)[0],60)
  self.assertEqual(p.target(c,58,[],1081)[0],40)
 def test_pending_drop_cancelled_by_rise(self):
  c=copy.deepcopy(DEFAULTS);c['fall_delay']=30;p=Cooling()
  p.target(c,72,[],1000);p.target(c,64,[],1010)
  self.assertEqual(p.target(c,72,[],1020)[0],100)   # back up: timer cleared
  self.assertEqual(p.target(c,64,[],1030)[0],100)
  self.assertEqual(p.target(c,64,[],1059)[0],100)   # only 29 s since new pending drop
if __name__=='__main__':unittest.main()
