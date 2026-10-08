import json,os,re,sys,tempfile,unittest
from pathlib import Path
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,presence
from storage import DiskMonitor,stable_identity,eon_bridge_type

ROOT=Path(__file__).resolve().parents[1]
USB='/sys/devices/platform/scb/fd500000.pcie/pci0000:00/0000:00:00.0/0000:01:00.0/usb2/2-2/2-2.2/2-2.2:1.0'
def scsi(host,lun,name): return '%s/host%d/target%d:0:0/%d:0:0:%d/block/%s'%(USB,host,host,host,lun,name)

class LunIdentity(unittest.TestCase):
 def test_two_luns_behind_one_bridge_have_distinct_identities(self):
  a=stable_identity(scsi(2,0,'sdc')); b=stable_identity(scsi(2,1,'sdd'))
  self.assertNotEqual(a,b)
  self.assertEqual(a,USB)            # LUN 0 keeps the identity it had before this fix
  self.assertTrue(b.startswith(USB))
 def test_identity_does_not_depend_on_the_scsi_host_number(self):
  self.assertEqual(stable_identity(scsi(2,1,'sdd')),stable_identity(scsi(5,1,'sdd')))
 def test_identity_does_not_depend_on_the_device_letter(self):
  self.assertEqual(stable_identity(scsi(2,1,'sdd')),stable_identity(scsi(2,1,'sdg')))
 def test_non_usb_paths_are_unchanged(self):
  p='/sys/devices/platform/x/ata1/host0/target0:0:0/0:0:0:1/block/sda'
  self.assertEqual(stable_identity(p),p)
 def test_presence_snapshot_sees_both_disks_on_one_bridge(self):
  """The real bug: sdc and sdd overwrote each other, so sdc was missing from `present`."""
  root=Path(tempfile.mkdtemp()); blk=root/'sys'/'block'; blk.mkdir(parents=True)
  base=root/'devices'/'usb2'/'2-2'/'2-2.2'/'2-2.2:1.0'/'host2'/'target2:0:0'
  for lun,name in ((0,'sdc'),(1,'sdd')):
   d=base/('2:0:0:%d'%lun)/'block'/name; (d/'device').mkdir(parents=True)
   (d/'stat').write_text('1 0 8 0 2 0 16 0 0 0 0 0 0 0 0 0 0\n'); (d/'size').write_text('2000409264\n')
   (d/'device'/'model').write_text('SATA\n'); (d/'device'/'vendor').write_text('Pinas\n')
   (blk/name).symlink_to(d)
  snap=presence.snapshot(blk)
  self.assertEqual(sorted(v['name'] for v in snap.values()),['sdc','sdd'])

class AutoBridge(unittest.TestCase):
 def sysfs(self,vid,pid,port='2-2.2'):
  root=Path(tempfile.mkdtemp()); dev=root/'usb2'/'2-2'/port; (dev/(port+':1.0')).mkdir(parents=True)
  (dev/'idVendor').write_text(vid+'\n'); (dev/'idProduct').write_text(pid+'\n')
  return str(dev/(port+':1.0'))
 def test_eon_bridges_get_sat(self):
  self.assertEqual(eon_bridge_type({'identity':self.sysfs('174e','1155')}),'sat')
  self.assertEqual(eon_bridge_type({'identity':self.sysfs('1741','1156','2-2.4')}),'sat')
  self.assertEqual(eon_bridge_type({'identity':self.sysfs('174E','1155')+'#0:0:1'}),'sat')   # LUN suffix and case
 def test_other_bridges_and_bad_input_get_nothing(self):
  self.assertIsNone(eon_bridge_type({'identity':self.sysfs('0781','558c','2-1')}))
  self.assertIsNone(eon_bridge_type({'identity':'/nonexistent/usb9/9-9/9-9:1.0'}))
  self.assertIsNone(eon_bridge_type({'identity':''})); self.assertIsNone(eon_bridge_type({}))

 def rows(self):
  eon=self.sysfs('174e','1155'); other=self.sysfs('0781','558c','2-1'); empty=self.sysfs('1741','1156','2-4')
  mk=lambda n,i,s=1000204886016: {'name':n,'device':'/dev/'+n,'model':'SATA','size':s,'identity':i,'power':'Unknown','temperature':None}
  return [mk('sda',other,500107837440),mk('sdb',empty,0),mk('sdc',eon),mk('sdd',eon+'#0:0:1')]
 def monitor(self,calls):
  data={'temperature':{'current':31},'serial_number':'ABCD1234','smart_status':{'passed':True},'ata_smart_attributes':{'table':[]}}
  def run(cmd,**kw):
   calls.append(cmd)
   class R: pass
   r=R(); r.returncode=0; r.stdout=json.dumps(data); return r
  return DiskMonitor(run)
 def test_eon_disks_are_monitored_with_no_settings_and_others_are_not(self):
  calls=[]; m=self.monitor(calls); out={d['name']:d for d in m.poll({},self.rows())}
  for n in ('sdc','sdd'):
   self.assertEqual(out[n]['bridge_type'],'sat'); self.assertTrue(out[n]['bridge_auto'])
   self.assertEqual(out[n]['health'],'Passed'); self.assertEqual(out[n]['temperature'],31)
  self.assertIsNone(out['sda']['bridge_type']); self.assertTrue(out['sda']['message'].startswith('Select verified'))
  self.assertEqual(out['sdb']['power'],'No media')
  self.assertEqual(sorted(c[-1] for c in calls),['/dev/sdc','/dev/sdd'])      # nothing is sent to sda or the empty bay
  for c in calls: self.assertEqual(c[c.index('-d')+1],'sat'); self.assertIn('standby,99,98',c)   # explicit type, no-wake guard
 def test_each_disk_keeps_its_own_cache_entry(self):
  m=self.monitor([]); rows=m.poll({},self.rows())
  self.assertEqual(len(m.cache),4)                      # sda, sdb, sdc and sdd each keep their own entry
  ident={d['name']:d['identity'] for d in rows}; self.assertNotEqual(ident['sdc'],ident['sdd'])
 def test_user_choice_beats_auto_and_ignore_is_honoured(self):
  calls=[]; m=self.monitor(calls); out={d['name']:d for d in m.poll({'sdc':'sat,12','sdd':'ignore'},self.rows())}
  self.assertEqual(out['sdc']['bridge_type'],'sat,12'); self.assertFalse(out['sdc']['bridge_auto'])
  self.assertEqual(out['sdd']['power'],'Ignored'); self.assertEqual([c[-1] for c in calls],['/dev/sdc'])
 def test_effective_type_is_used_for_tests(self):
  with app.lock: saved=app.cfg; app.state['disks']=[{'name':'sdc','bridge_type':'sat'},{'name':'sdd','bridge_type':None}]
  try:
   self.assertEqual(app.drive_type('sdc'),'sat'); self.assertIsNone(app.drive_type('sdd')); self.assertIsNone(app.drive_type('sdz'))
   with app.lock: app.cfg=dict(saved,drive_types={'sdc':'sat,12'})
   self.assertEqual(app.drive_type('sdc'),'sat,12')
  finally:
   with app.lock: app.cfg=saved; app.state['disks']=[]
 def test_manual_test_endpoint_accepts_auto_disks_only(self):
  app.app.testing=True; c=app.app.test_client()
  with app.lock: app.state['disks']=[{'name':'sdc','bridge_type':'sat'},{'name':'sda','bridge_type':None}]
  try:
   ok=c.post('/api/smart/test',json={'name':'sdc','test':'short'},headers={'X-Eon-Request':'1'})
   self.assertEqual(ok.status_code,200)
   no=c.post('/api/smart/test',json={'name':'sda','test':'short'},headers={'X-Eon-Request':'1'})
   self.assertEqual(no.status_code,400)
  finally:
   with app.lock: app.state['disks']=[]
   while not app.jobs.empty(): app.jobs.get_nowait()

class SettingsTakeEffect(unittest.TestCase):
 def setUp(self):
  app.app.testing=True; self.c=app.app.test_client(); self.h={'X-Eon-Request':'1'}
  with app.lock: self.saved=app.cfg
  app.wake_now.clear()
 def tearDown(self):
  with app.lock: app.cfg=self.saved; app.state['disks']=[]
  app.wake_now.clear()
  while not app.jobs.empty(): app.jobs.get_nowait()
 def save(self,**changes):
  c=app.configuration(); c.update(changes); return self.c.post('/api/config',json=c,headers=self.h)
 def test_changing_a_drive_setting_triggers_an_immediate_recheck(self):
  self.assertEqual(self.save(drive_types={'sda':'ignore'}).status_code,200); self.assertTrue(app.wake_now.is_set())
 def test_saving_unrelated_settings_does_not(self):
  self.save(drive_types={'sda':'ignore'}); app.wake_now.clear()
  self.assertEqual(self.save(brightness=70).status_code,200); self.assertFalse(app.wake_now.is_set())
 def test_manual_test_is_refused_for_an_empty_bay(self):
  with app.lock: app.state['disks']=[{'name':'sdb','bridge_type':'sat','power':'No media'},{'name':'sdc','bridge_type':'sat','power':'Active'}]
  self.assertEqual(self.c.post('/api/smart/test',json={'name':'sdb','test':'short'},headers=self.h).status_code,400)
  self.assertEqual(self.c.post('/api/smart/test',json={'name':'sdc','test':'short'},headers=self.h).status_code,200)

class PageScript(unittest.TestCase):
 """The rc12 regression: app.js used an element that index.html no longer had, the refresh threw, and the drive cards never drew."""
 def test_every_element_the_script_uses_exists_in_the_page(self):
  js=(ROOT/'static'/'app.js').read_text(); html=(ROOT/'templates'/'index.html').read_text()
  ids=set(re.findall(r"\$\('#([A-Za-z_][\w-]*)'\)",js))|{'cpu_curve','disk_curve'}
  missing=sorted(i for i in ids if 'id="%s"'%i not in html)
  self.assertEqual(missing,[],'app.js uses ids missing from index.html: '+', '.join(missing))
 def test_every_tab_has_a_panel(self):
  html=(ROOT/'templates'/'index.html').read_text()
  self.assertEqual(sorted(re.findall(r'data-tab="(\w+)"',html)),sorted(re.findall(r'<section class="panel[^"]*" id="(\w+)"',html)))
 def test_version_looks_like_a_version(self): self.assertRegex(app.VERSION,r'^\d+\.\d+\.\d+(-rc\d+)?$')
 @unittest.skipUnless(all((ROOT/f).exists() for f in ('config.yaml','Dockerfile','CHANGELOG.md')),'packaging files are not copied into the built image; checked on the source tree')
 def test_version_is_consistent_everywhere(self):
  v=re.search(r'version: "([^"]+)"',(ROOT/'config.yaml').read_text()).group(1)
  self.assertEqual(app.VERSION,v); self.assertIn('ARG BUILD_VERSION='+v,(ROOT/'Dockerfile').read_text()); self.assertTrue((ROOT/'CHANGELOG.md').read_text().startswith('# '+v))

if __name__=='__main__': unittest.main()
