import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alerts import sync,notification_id
class Rec:
 def __init__(self): self.made=[];self.gone=[];self.fail=False
 def notify(self,m):
  if self.fail: raise RuntimeError('HA down')
  self.made.append(m)
 def dismiss(self,m): self.gone.append(m)
class AlertTests(unittest.TestCase):
 def test_standing_condition_raises_once_dismisses_and_can_return(self):
  r=Rec();n={}
  for present in (True,True,False,True):
   sync(n,['fan fault'] if present else [],[],r.notify,r.dismiss)
  self.assertEqual(r.made,['fan fault','fan fault']);self.assertEqual(r.gone,['fan fault'])
 def test_occurrence_raised_once_never_dismissed_and_pruned_when_gone(self):
  r=Rec();n={}
  sync(n,[],['Disk disappeared: sdb'],r.notify,r.dismiss);sync(n,[],['Disk disappeared: sdb'],r.notify,r.dismiss)
  self.assertEqual(r.made,['Disk disappeared: sdb'])
  sync(n,[],[],r.notify,r.dismiss);self.assertEqual(r.gone,[]);self.assertEqual(n,{})
 def test_failed_notify_is_retried(self):
  r=Rec();n={};r.fail=True
  with self.assertRaises(RuntimeError): sync(n,['x'],[],r.notify,r.dismiss)
  self.assertEqual(n,{});r.fail=False;sync(n,['x'],[],r.notify,r.dismiss);self.assertEqual(r.made,['x'])
 def test_ids_are_stable_and_distinct(self):
  self.assertEqual(notification_id('a'),notification_id('a'));self.assertNotEqual(notification_id('a'),notification_id('b'))
if __name__=='__main__':unittest.main()
