import os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,presence

IDENT_A='/sys/x/usb1/1-1/1-1.2/1-1.2:1.0'   # a stable USB-port identity, as stable_identity() would produce
IDENT_B='/sys/x/usb1/1-1/1-1.3/1-1.3:1.0'

def disk(name,io,model='WD40',identity=IDENT_A): return dict(name=name,vendor='ATA',model=model,identity=identity,io=io,size=4000787030016)

class PresenceFiles(unittest.TestCase):
 def test_snapshot_keys_by_stable_identity_not_device_letter(self):
  root=Path(tempfile.mkdtemp());d=root/'sda';(d/'device').mkdir(parents=True)
  (d/'stat').write_text('  10 0 80 5 20 0 160 9 0 3 14 0 0 0 0 0 0\n');(d/'size').write_text('7814037168\n')
  (d/'device'/'model').write_text('ST4000\n');(d/'device'/'vendor').write_text('ATA\n')
  result=presence.snapshot(root); s=next(iter(result.values()))
  self.assertEqual(len(result),1);self.assertEqual(s['io'],(10,20));self.assertEqual(s['model'],'ST4000');self.assertEqual(s['name'],'sda')
 def test_woken_only_when_counters_move(self):
  a={IDENT_A:disk('sda',(1,1)),IDENT_B:disk('sdb',(5,5))};b={IDENT_A:disk('sda',(1,1)),IDENT_B:disk('sdb',(6,5))}
  self.assertEqual(presence.woken(a,b),[IDENT_B]);self.assertEqual(presence.woken(a,a),[])
 def test_missing_counters_never_trigger(self):
  self.assertEqual(presence.woken({IDENT_A:disk('sda',None)},{IDENT_A:disk('sda',(1,1))}),[])
 def test_describe_names_model_size_port(self):
  self.assertEqual(presence.describe(disk('sdb',(1,1))),'sdb ATA WD40 (4001 GB, USB port 1-1.2)')
 def test_a_device_rename_looks_like_no_change_at_all(self):
  """The actual bug this module exists to prevent: sdb becomes sdc on the same USB port
  (a kernel rename across a reconnect) must not register as disappeared+appeared."""
  before={IDENT_A:disk('sdb',(1,1))}; after={IDENT_A:disk('sdc',(1,1))}
  self.assertEqual(presence.disappeared(before,after),[]);self.assertEqual(presence.appeared(before,after),[])

class WatchWorker(unittest.TestCase):
 def run_watch(self,snaps,rows):
  app.stop.clear();app.wake_now.clear();app.WATCH_SECONDS=0.01
  with app.lock: app.state.update(disks=rows,events=[]);app.state.pop('disk_checked',None)
  it=iter(snaps);last=[snaps[0]];calls=[0]
  def fake():
   calls[0]+=1
   try: last[0]=next(it)
   except StopIteration: pass
   return last[0]
  with patch('presence.snapshot',side_effect=fake):
   t=threading.Thread(target=app.watch_worker);t.start()
   deadline=time.time()+10   # wait for the outcome, not for a fixed time (slow CI safe)
   while time.time()<deadline and not app.wake_now.is_set() and calls[0]<len(snaps)+4: time.sleep(0.01)
   woke=app.wake_now.is_set();app.stop.set();t.join(3)
  app.stop.clear();return woke,[e['message'] for e in app.snap()['events']]
 def test_touched_sleeping_disk_requests_immediate_poll(self):
  woke,ev=self.run_watch([{IDENT_A:disk('sda',(1,1))},{IDENT_A:disk('sda',(2,1))}],[{'name':'sda','identity':IDENT_A,'power':'Standby'}])
  self.assertTrue(woke);self.assertEqual(ev,[])
 def test_touched_active_disk_does_not_add_polls(self):
  woke,ev=self.run_watch([{IDENT_A:disk('sda',(1,1))},{IDENT_A:disk('sda',(2,1))}],[{'name':'sda','identity':IDENT_A,'power':'Active'}])
  self.assertFalse(woke)
 def test_first_trigger_not_blocked_by_low_uptime(self):
  with patch('time.monotonic',return_value=5.0):
   woke,ev=self.run_watch([{IDENT_A:disk('sda',(1,1))},{IDENT_A:disk('sda',(2,1))}],[{'name':'sda','identity':IDENT_A,'power':'Standby'}])
  self.assertTrue(woke)
 def test_disk_vanishing_during_triggered_poll_is_still_reported(self):
  app.stop.clear();app.wake_now.clear();app.WATCH_SECONDS=0.01
  with app.lock: app.state.update(disks=[{'name':'sda','identity':IDENT_A,'power':'Standby'}],events=[]);app.state['disk_checked']=None
  seq=[{IDENT_A:disk('sda',(1,1))},{IDENT_A:disk('sda',(2,1))}];calls=[0]
  def fake():
   calls[0]+=1;return seq[min(calls[0],len(seq))-1] if calls[0]<=len(seq) else {}
  with patch('presence.snapshot',side_effect=fake):
   t=threading.Thread(target=app.watch_worker);t.start()
   deadline=time.time()+10
   while time.time()<deadline and not app.wake_now.is_set(): time.sleep(0.01)
   self.assertTrue(app.wake_now.is_set())
   with app.lock: app.state['disk_checked']=1.0          # the triggered poll finishes; disk is already gone
   while time.time()<deadline and not any('disappeared' in e['message'] for e in app.snap()['events']): time.sleep(0.01)
   found=[e['message'] for e in app.snap()['events'] if 'disappeared' in e['message']];app.stop.set();t.join(3)
  app.stop.clear();self.assertEqual(len(found),1)
 def test_idle_sleeping_disk_costs_nothing(self):
  woke,ev=self.run_watch([{IDENT_A:disk('sda',(1,1))}],[{'name':'sda','identity':IDENT_A,'power':'Standby'}]);self.assertFalse(woke)
 def test_vanished_disk_is_reported_with_identity_and_refreshes_state(self):
  woke,ev=self.run_watch([{IDENT_A:disk('sda',(1,1)),IDENT_B:disk('sdb',(1,1),'WD40EFRX',IDENT_B)},{IDENT_A:disk('sda',(1,1))}],
                          [{'name':'sdb','identity':IDENT_B,'power':'Active'}])
  self.assertTrue(woke);self.assertEqual(len(ev),1);self.assertIn('Disk disappeared: sdb ATA WD40EFRX',ev[0]);self.assertIn('USB port 1-1.3',ev[0])
 def test_disk_renamed_between_polls_does_not_falsely_report_disappeared_or_appeared(self):
  """Same physical drive, same port, kernel gave it a new letter (sdb -> sdc). No event, no confusion."""
  woke,ev=self.run_watch([{IDENT_A:disk('sdb',(1,1))},{IDENT_A:disk('sdc',(1,1))}],[{'name':'sdb','identity':IDENT_A,'power':'Active'}])
  self.assertEqual(ev,[])
if __name__=='__main__':unittest.main()
