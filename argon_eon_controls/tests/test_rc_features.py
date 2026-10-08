import copy,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,i2c_setup
from reliability import DEFAULTS,Cooling,validate
from storage import DiskMonitor

def row(n,size=1000): return dict(name=n,identity=n,model='m',device='/dev/'+n,size=size,temperature=None,power='Unknown')

class Drives(unittest.TestCase):
 def poll(self,types,rows):
  def run(*a,**k): raise AssertionError('no disk command may be sent')
  return DiskMonitor(run).poll(types,rows)
 def test_empty_bay_and_ignored_disk_send_no_command_and_hold_no_floor(self):
  rows=self.poll({'sdb':'ignore'},[row('sdb'),row('sdc',0)])
  self.assertEqual([r['power'] for r in rows],['Ignored','No media'])
  c=copy.deepcopy(DEFAULTS);c['fall_delay']=0;self.assertEqual(Cooling().target(c,40,rows,1000)[0],0)
 def test_unconfigured_real_disk_still_holds_the_floor(self):
  rows=self.poll({},[row('sda')]);c=copy.deepcopy(DEFAULTS);c['fall_delay']=0
  self.assertEqual(Cooling().target(c,40,rows,1000)[0],40)
 def test_ignore_is_a_valid_setting(self):
  c=copy.deepcopy(DEFAULTS);c['drive_types']={'sdb':'ignore'};validate(c)

class SmartReason(unittest.TestCase):
 def test_failure_message_carries_smartctls_own_reason(self):
  data={'smartctl':{'messages':[{'string':'Smartctl open device: /dev/sda failed: Operation not permitted','severity':'error'}]}}
  def run(cmd,**k):
   class R: pass
   r=R();r.returncode=2;r.stdout=json.dumps(data);return r
  d=DiskMonitor(run).poll({'sda':'sat'},[row('sda')])[0]
  self.assertIn('Operation not permitted',d['message']);self.assertIn('exit 2',d['message']);self.assertIn('sat',d['message'])

class Reasons(unittest.TestCase):
 def cfg(self,**k):
  c=copy.deepcopy(DEFAULTS);c['fall_delay']=0;c.update(k);return c
 def test_names_the_cpu_when_cpu_decides(self):
  self.assertEqual(Cooling().target(self.cfg(),64,[],1000),(60,'CPU 64°C'))
 def test_names_the_disk_when_a_disk_decides(self):
  d=dict(name='sda',power='Active',temperature=46,sample_mono=1000.)
  w,why=Cooling().target(self.cfg(),40,[d],1000);self.assertEqual(w,40);self.assertEqual(why,'Disk sda 46°C')
 def test_names_the_unreadable_disk_holding_the_floor(self):
  w,why=Cooling().target(self.cfg(minimum_unmonitored=40),40,[dict(name='sda',power='Unknown',temperature=None)],1000)
  self.assertEqual(w,40);self.assertIn('cannot read temperature of sda',why)
 def test_floor_can_be_switched_off(self):
  c=self.cfg(minimum_unmonitored=0);validate(c)
  self.assertEqual(Cooling().target(c,40,[dict(name='sda',power='Unknown',temperature=None)],1000)[0],0)
 def test_modes_and_test_have_plain_labels(self):
  self.assertEqual(Cooling().target(self.cfg(mode='off'),70,[],1000),(0,'Fan mode is off'))
  self.assertEqual(Cooling().target(self.cfg(),40,[],1000,override=75),(75,'Temporary fan test'))

class Mount(unittest.TestCase):
 def fake(self,fail_first):
  calls=[]
  def run(cmd,**k):
   calls.append(cmd)
   class R: pass
   r=R();r.stdout='';r.stderr='';r.returncode=0
   if cmd[0]=='blkid': r.stdout='/dev/mmcblk0p1\n'
   elif cmd[0]=='mount' and len([c for c in calls if c[0]=='mount'])<=fail_first: r.returncode=32;r.stderr='wrong fs type, missing codepage'
   elif cmd[0]=='dmesg': r.stdout='FAT-fs (mmcblk0p1): IO charset iso8859-1 not found\n'
   return r
  return run,calls
 def test_all_mounts_fail_reports_every_attempt_and_kernel_reason(self):
  tmp=Path(tempfile.mkdtemp());mk=tmp/'m';rep=[];run,calls=self.fake(99)
  with patch('subprocess.run',side_effect=run):
   with self.assertRaises(RuntimeError) as cm: i2c_setup.ensure(mk,device=tmp/'none',mountpoint=str(tmp/'mnt'),report=rep,host_boot=tmp/'nohost')
  msg=str(cm.exception);self.assertIn('missing codepage',msg);self.assertIn('iocharset=ascii',msg);self.assertIn('IO charset',msg)
  self.assertFalse(mk.exists());self.assertEqual(len(rep),len(i2c_setup.OPTION_SETS))
 def test_later_option_set_can_succeed(self):
  tmp=Path(tempfile.mkdtemp());mnt=tmp/'mnt';mk=tmp/'m';run,calls=self.fake(1);rep=[]
  with patch('subprocess.run',side_effect=run):
   self.assertEqual(i2c_setup.ensure(mk,device=tmp/'none',mountpoint=str(mnt),report=rep,host_boot=tmp/'nohost'),'reboot')
  self.assertTrue(mk.exists());self.assertIn('dtparam=i2c_arm=on',(mnt/'config.txt').read_text());self.assertEqual([c[0] for c in calls].count('umount'),1)
 def test_uses_hosts_own_boot_mount_without_mounting(self):
  tmp=Path(tempfile.mkdtemp());host=tmp/'hb';host.mkdir();(host/'config.txt').write_text('a=1\n')
  with patch('subprocess.run',side_effect=AssertionError('must not run')):
   self.assertEqual(i2c_setup.ensure(tmp/'m',device=tmp/'none',host_boot=host),'reboot')
  self.assertIn('i2c_arm=on',(host/'config.txt').read_text())
 def test_missing_partition_raises_and_writes_no_marker(self):
  tmp=Path(tempfile.mkdtemp());mk=tmp/'m'
  class B: stdout='';returncode=0;stderr=''
  with patch('subprocess.run',return_value=B()):
   with self.assertRaises(RuntimeError): i2c_setup.ensure(mk,device=tmp/'none',host_boot=tmp/'nohost')
  self.assertFalse(mk.exists())
 def test_permission_error_on_host_probe_falls_through_not_crashes(self):
  tmp=Path(tempfile.mkdtemp());mk=tmp/'m';host=tmp/'hb'  # host dir deliberately not created: real Path.exists() -> False, not an error
  real=Path.exists
  def flaky(self):
   if str(self)==str(host/'config.txt'): raise PermissionError(13,'denied')
   return real(self)
  class B: stdout='/dev/mmcblk0p1\n';returncode=0;stderr=''
  with patch.object(Path,'exists',flaky), patch('subprocess.run',return_value=B()):
   # host probe denied -> falls through to mounting the partition itself, which here succeeds
   self.assertEqual(i2c_setup.ensure(mk,device=tmp/'none',mountpoint=str(tmp/'mnt'),host_boot=host),'reboot')
  self.assertTrue(mk.exists())

class Workers(unittest.TestCase):
 def test_crashing_worker_is_restarted_not_left_dead(self):
  app.stop.clear();n=[0];done=threading.Event()
  def flaky():
   n[0]+=1
   if n[0]<3: raise ValueError('boom')
   done.set()
  with patch.object(app.stop,'wait',lambda t=None:False):
   t=threading.Thread(target=app.guarded(flaky));t.start();t.join(5)
  self.assertTrue(done.is_set());self.assertEqual(n[0],3);app.stop.clear()
 def test_health_fails_when_a_worker_is_dead(self):
  app.app.testing=True;dead=threading.Thread(target=lambda:None);dead.start();dead.join()
  old=(app.heartbeat,list(app.workers));app.heartbeat=time.monotonic();app.workers[:]=[dead]
  try: self.assertEqual(app.app.test_client().get('/health').status_code,503)
  finally: app.heartbeat=old[0];app.workers[:]=old[1]
 def test_fan_is_live_without_confirmation(self): self.assertTrue(app.state['commissioned'])

class ScreenTester(unittest.TestCase):
 def setUp(self): app.app.testing=True;self.c=app.app.test_client();self.h={'X-Eon-Request':'1'}
 def test_every_test_pattern_previews_as_png(self):
  for p in ('white','black','checker','rings'):
   r=self.c.get('/api/oled/preview/%s.png'%p);self.assertEqual(r.status_code,200,p);self.assertTrue(r.data.startswith(b'\x89PNG'))
 def test_pattern_endpoint_sets_state_and_wakes_display(self):
  app.page_wake.clear();r=self.c.post('/api/oled/pattern/checker',json={},headers=self.h)
  self.assertEqual(r.status_code,200);self.assertEqual(app.snap()['test_pattern'],'checker');self.assertTrue(app.page_wake.is_set())
  app.page_wake.clear()
 def test_unknown_pattern_is_404(self): self.assertEqual(self.c.post('/api/oled/pattern/nope',json={},headers=self.h).status_code,404)
 def test_recheck_wakes_disk_poll(self):
  app.wake_now.clear();self.assertEqual(self.c.post('/api/disks/recheck',json={},headers=self.h).status_code,200);self.assertTrue(app.wake_now.is_set());app.wake_now.clear()
 def test_pattern_draws_without_any_app_state(self):
  from hardware import test_pattern
  for p in ('white','black','checker','rings'):
   im=test_pattern(p); self.assertEqual(im.size,(128,64))
  self.assertIsNotNone(test_pattern('white').getbbox())  # white pattern actually lights pixels
  self.assertIsNone(test_pattern('black').getbbox())     # black pattern is empty

class TelemetryThrottle(unittest.TestCase):
 def test_throttle_only_refetches_after_the_interval(self):
  import app
  calls=[]
  def fake_supervisor(path,body=None):
   calls.append(path); return {'data':{}}
  app.stop.clear(); app.cfg=copy.deepcopy(DEFAULTS)
  # a clock that advances 1s per loop iteration regardless of how many times monotonic() is read within it
  clock=[0.]
  def fake_monotonic(): return clock[0]
  iterations=[0]
  def fake_wait(t=None):
   iterations[0]+=1; clock[0]+=1000 if iterations[0]==5 else 1  # jump past the 900s mark once, mid-run
   if iterations[0]>=8: app.stop.set()
   return False
  with patch('app.supervisor',fake_supervisor), patch('app.STANDALONE',False), \
       patch('app.usb_devices',return_value=[]), patch('app.metrics',return_value={}), \
       patch.object(app,'hw',type('H',(),{'rtc_status':lambda s:{}})()), \
       patch('time.monotonic',fake_monotonic), \
       patch.object(app.stop,'wait',fake_wait):
   app.telemetry()
  # fetched once at t=0 (host_due starts at 0, so due immediately), then again only once the 900s mark is crossed
  self.assertEqual(calls.count('/host/info'),2)
  self.assertEqual(calls.count('/network/info'),2)
if __name__=='__main__':unittest.main()

class DriveRenameStability(unittest.TestCase):
 """Regression test for a real failure seen in the field: a USB SATA bridge got renamed by the
 kernel (e.g. sdb -> sdc) between polls. Before this fix, that changed the drive's `identity`,
 which reset its cached health/temperature and let the same failing drive alert twice under two
 device names. identity must now depend on the USB port, not the kernel-assigned letter."""
 def sysfs_path(self,letter,port='2-2.2'):
  return ('/sys/devices/platform/scb/fd500000.pcie/pci0000:00/0000:00:00.0/0000:01:00.0/usb2/'
          '%s/%s/%s:1.0/host1/target1:0:0/1:0:0:0/block/sd%s'%(port.split('.')[0],port,port,letter))
 def test_same_port_same_identity_across_a_rename(self):
  from storage import stable_identity
  self.assertEqual(stable_identity(self.sysfs_path('b')),stable_identity(self.sysfs_path('c')))
 def test_different_ports_get_different_identities(self):
  from storage import stable_identity
  self.assertNotEqual(stable_identity(self.sysfs_path('b','2-2.2')),stable_identity(self.sysfs_path('c','2-2.4')))
 def test_unrecognized_topology_falls_back_to_the_full_path(self):
  from storage import stable_identity
  odd='/sys/devices/virtual/block/sdz'
  self.assertEqual(stable_identity(odd),odd)
 def test_cache_survives_a_rename_no_health_history_lost(self):
  m=DiskMonitor(lambda *a,**k: (_ for _ in ()).throw(AssertionError('no command needed for this check')))
  ident=self.sysfs_path('b')[:-len('/block/sdb')]  # what inventory() would now produce for either letter
  m.cache={ident:{'identity':ident,'last_temperature':41,'last_measured':1000.}}
  seen_as_sdc=dict(name='sdc',identity=ident,model='SATA',device='/dev/sdc',size=1,temperature=None,power='Unknown')
  d=m.poll({},[seen_as_sdc])[0]
  self.assertEqual(d['last_temperature'],41)  # NOT wiped just because the device letter changed
 def test_smart_event_does_not_double_alert_across_a_rename(self):
  from storage import smart_event
  ident=self.sysfs_path('b')[:-len('/block/sdb')]
  bad=dict(name='sdb',identity=ident,model='SATA',size=1000107837440,serial_tail='BKGF',
           power='Active',health='Warning',message='2944 pending sectors')
  alerted={}
  first=smart_event(bad,alerted); self.assertIsNotNone(first)
  renamed=dict(bad,name='sdc')  # same physical drive, kernel gave it a new letter; identity unchanged
  self.assertIsNone(smart_event(renamed,alerted))  # must NOT alert again
if __name__=='__main__':unittest.main()
