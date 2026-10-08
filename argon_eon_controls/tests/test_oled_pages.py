import os,re,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import ImageDraw
import hardware,reliability
from hardware import render_page,duration,drive_row
from test_entities import FLEET,disk

def texts(page,state,cfg=None):
 seen=[]; orig=ImageDraw.ImageDraw.text
 def rec(self,xy,text,*a,**k): seen.append(str(text)); return orig(self,xy,text,*a,**k)
 with patch.object(ImageDraw.ImageDraw,'text',rec): img=render_page(page,state,cfg or {})
 return seen,img

class Pages(unittest.TestCase):
 def test_every_page_renders_a_non_blank_panel_in_bounds_with_awkward_input(self):
  for page in sorted(reliability.PAGES):
   for state in ({},{'disks':[]},{'disks':FLEET,'fan':40,'reason':'Minimum 40%: cannot read temperature of sda','metrics':{'uptime_seconds':400000,'cpu_percent':3,'memory_percent':61}}):
    _,img=texts(page,state); self.assertEqual(img.size,(128,64)); self.assertIsNotNone(img.getbbox(),page)
 def test_no_line_is_longer_than_the_panel_width(self):
  for page in ('storage','alerts','cooling'):
   seen,_=texts(page,{'disks':FLEET+[disk('sde'),disk('sdf')],'fan':100,'reason':'x'*200}); self.assertTrue(seen)
   for t in seen: self.assertLessEqual(len(t),21)
 def test_storage_lists_only_monitored_drives(self):
  seen,_=texts('storage',{'disks':FLEET}); self.assertEqual(seen,['STORAGE','sdc  34C  WARN','sdd  33C  OK'])
 def test_storage_with_nothing_monitored_says_so(self):
  seen,_=texts('storage',{'disks':[FLEET[0],FLEET[1]]}); self.assertEqual(seen,['STORAGE','No drives monitored'])
 def test_storage_shows_four_drives_without_the_title(self):
  seen,_=texts('storage',{'disks':[disk('sd%s'%c) for c in 'cdef']}); self.assertEqual(len(seen),4); self.assertNotIn('STORAGE',seen)
 def test_a_sleeping_drive_is_marked(self):
  self.assertEqual(drive_row(disk('sdc',power='Standby',temperature=None,last_temperature=31)),'sdc  31C  OK zz')
  self.assertEqual(drive_row(disk('sdc',temperature=None,last_temperature=None,health='Unknown')),'sdc  --C  ?')
 def test_alerts_names_the_drive_and_the_problem(self):
  seen,_=texts('alerts',{'disks':FLEET}); self.assertEqual(seen,['sdc WARNING','2944 pending sectors'])
 def test_alerts_all_clear(self):
  seen,_=texts('alerts',{'disks':[disk('sdd')]}); self.assertEqual(seen,['DRIVE ALERTS','No drive problems','1 drive monitored'])
  seen,_=texts('alerts',{'disks':[disk('sdc'),disk('sdd')]}); self.assertEqual(seen[2],'2 drives monitored')
 def test_alerts_falls_back_to_the_message_when_there_are_no_counts(self):
  seen,_=texts('alerts',{'disks':[disk('sdc',health='Failed',message='overall SMART status FAILED')]}); self.assertEqual(seen,['sdc FAILED','overall SMART status'])
 def test_cooling_shows_fan_and_reason_without_the_degree_sign(self):
  seen,_=texts('cooling',{'fan':40,'reason':'Minimum 40%: cannot read temperature of sda'})
  self.assertEqual(seen,['COOLING  Fan 40 %','Minimum 40%: cannot','read temperature of','sda'])      # the whole reason fits, nothing cut off
  self.assertNotIn('\u00b0',''.join(seen))
  seen,_=texts('cooling',{'fan':0,'reason':'CPU 38\u00b0C'}); self.assertEqual(seen,['COOLING  Fan 0 %','CPU 38C'])
 def test_uptime(self):
  self.assertEqual(duration(None),'--'); self.assertEqual(duration(75),'1m 15s'); self.assertEqual(duration(3*3600+5*60),'3h 5m'); self.assertEqual(duration(3*86400+4*3600+12*60),'3d 4h 12m')
  seen,_=texts('uptime',{'metrics':{'uptime_seconds':3*86400+4*3600+12*60,'cpu_percent':3,'memory_percent':61}}); self.assertEqual(seen,['UPTIME','3d 4h 12m','CPU 3%  RAM 61%'])

class PageNamesAgree(unittest.TestCase):
 def test_script_labels_match_the_servers_page_list(self):
  js=(Path(__file__).resolve().parents[1]/'static'/'app.js').read_text()
  names=dict(re.findall(r"(\w+):'([^']+)'",re.search(r"const names=\{(.*?)\};",js).group(1)))
  self.assertEqual(set(names),set(reliability.PAGES))

if __name__=='__main__': unittest.main()
