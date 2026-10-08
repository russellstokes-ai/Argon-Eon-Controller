import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storage import DiskMonitor,smart_event
def attrs(**raw): return [{'id':i,'raw':{'value':v}} for i,v in raw.items()] if False else [{'id':int(k[1:]),'raw':{'value':v}} for k,v in raw.items()]
class Severity(unittest.TestCase):
 row={'name':'sdb','identity':'/sys/x/usb1/1-1/1-1.3/1-1.3:1.0/block/sdb','model':'WD40EFRX','device':'/dev/sdb','size':4000787030016,'temperature':None,'power':'Unknown'}
 def poll(self,code=0,passed=True,**raw):
  data={'temperature':{'current':40},'serial_number':'WX12AB34CD','smart_status':{'passed':passed},'ata_smart_attributes':{'table':attrs(**raw)}}
  def run(cmd,**kw):
   class R: pass
   r=R();r.returncode=code;r.stdout=json.dumps(data);return r
  return DiskMonitor(run).poll({'sdb':'sat'},[self.row])[0]
 def test_healthy(self):
  d=self.poll();self.assertEqual(d['health'],'Passed');self.assertIsNone(d['message']);self.assertEqual(d['serial_tail'],'34CD')
 def test_pending_sectors_warn(self):
  d=self.poll(a197=8);self.assertEqual(d['health'],'Warning');self.assertIn('8 pending sectors',d['message'])
 def test_uncorrectable_sectors_warn(self):
  self.assertEqual(self.poll(a198=2)['health'],'Warning')
 def test_failing_status_and_prefail_bit_fail(self):
  self.assertEqual(self.poll(code=8,passed=False)['health'],'Failed');self.assertEqual(self.poll(code=16)['health'],'Failed')
 def test_old_log_entries_are_notes_not_alerts(self):
  d=self.poll(code=64|128);self.assertEqual(d['health'],'Passed');self.assertEqual(len(d['smart_notes']),2)
 def test_event_names_the_exact_drive_once(self):
  alerted={};d=self.poll(a197=8);m=smart_event(d,alerted)
  for part in ('sdb','WD40EFRX','4001 GB','S/N ...34CD','USB port 1-1.3','8 pending sectors'): self.assertIn(part,m)
  self.assertTrue(m.startswith('SMART warning'));self.assertIsNone(smart_event(d,alerted))
 def test_escalation_realerts_and_failed_message_contains_failed(self):
  alerted={};smart_event(self.poll(a197=8),alerted)
  m=smart_event(self.poll(code=8,passed=False,a197=8),alerted);self.assertIn('failed',m.lower())
  self.assertIsNone(smart_event(self.poll(a197=8),alerted))   # Failed->Warning is not a new alert
 def test_standby_keeps_failed_without_repeating(self):
  alerted={};bad=self.poll(code=8,passed=False);smart_event(bad,alerted)
  self.assertIsNone(smart_event(dict(bad,power='Standby',temperature=None),alerted))
 def test_unknown_health_does_not_rearm(self):
  alerted={};smart_event(self.poll(a197=8),alerted)
  self.assertIsNone(smart_event(dict(self.poll(a197=8),health='Unknown'),alerted));self.assertIsNone(smart_event(self.poll(a197=8),alerted))
 def test_rearmed_after_recovery(self):
  alerted={};smart_event(self.poll(a197=8),alerted);smart_event(self.poll(),alerted)
  self.assertIsNotNone(smart_event(self.poll(a197=8),alerted))
if __name__=='__main__':unittest.main()
