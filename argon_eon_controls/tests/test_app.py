import copy,os,sys,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
os.environ['EON_DATA']=tempfile.mkdtemp()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from hardware import EonHardware,render_page
class WebTests(unittest.TestCase):
 def setUp(self): app.app.testing=True;self.c=app.app.test_client();app.cfg=copy.deepcopy(app.DEFAULTS)
 def test_post_requires_header(self): self.assertEqual(self.c.post('/api/config',json={}).status_code,403)
 def test_state_and_assets(self):
  for path in ['/','/api/status','/static/app.js','/static/style.css','/api/diagnostics']:
   with self.c.get(path) as r: self.assertEqual(r.status_code,200)
 def test_bad_settings_never_replace_good(self):
  self.assertEqual(self.c.post('/api/config',json={'manual_speed':-1},headers={'X-Eon-Request':'1'}).status_code,400)
  self.assertEqual(app.cfg['manual_speed'],40)
 def test_heartbeat_fails_when_cooling_stops(self):
  app.heartbeat=time.monotonic()-30;self.assertEqual(self.c.get('/health').status_code,503)
  app.heartbeat=time.monotonic();self.assertEqual(self.c.get('/health').status_code,200)
 def test_successful_settings(self):
  self.assertEqual(self.c.post('/api/config',json=app.DEFAULTS,headers={'X-Eon-Request':'1'}).status_code,200)
 def test_failed_fan_write_remains_unknown(self):
  class Bad:
   def set_fan(self,v): raise OSError('bus disconnected')
  app.stop.clear();app.hw=Bad();t=threading.Thread(target=app.cooling)
  with patch('app.cpu_temp',return_value=50):
   t.start();deadline=time.time()+10   # wait for the outcome, not a fixed time: slow builders must not fail this
   while time.time()<deadline and app.snap()['status']!='Fan command failed': time.sleep(.01)
   app.stop.set();t.join(2)
  self.assertIsNone(app.snap()['fan']);self.assertEqual(app.snap()['status'],'Fan command failed')
  app.stop.clear()
class PowerTests(unittest.TestCase):
 def test_observe_mode_no_host_request(self):
  app.cfg=copy.deepcopy(app.DEFAULTS)
  with patch('app.poweroff') as call:
   app.onbutton('shutdown',45);call.assert_not_called()
 def test_shutdown_calls_poweroff(self):
  app.cfg=copy.deepcopy(app.DEFAULTS);app.cfg['button_actions']=True
  with patch('app.poweroff') as call:
   app.onbutton('shutdown',45);call.assert_called_once_with()
 def test_reboot_disabled_independently(self):
  app.cfg=copy.deepcopy(app.DEFAULTS);app.cfg['button_actions']=True
  with patch('app.reboot') as call:
   app.onbutton('reboot',25);call.assert_not_called()
 def test_page_does_not_request_shutdown(self):
  with patch('app.poweroff') as call:
   app.onbutton('page',65);call.assert_not_called();self.assertTrue(app.page_wake.is_set())
class HardwareTests(unittest.TestCase):
 def test_upstream_oled_transfer_and_errors(self):
  class Bus:
   def __init__(self):self.blocks=[]
   def write_byte_data(self,*args):pass
   def write_i2c_block_data(self,addr,reg,data):self.blocks.append((addr,reg,len(data)))
  h=EonHardware();h.bus=Bus();h.oled_image(render_page('clock',{},{}))
  self.assertEqual(len(h.bus.blocks),32)
  self.assertTrue(all(x==(0x3c,0x6a,32) for x in h.bus.blocks))
  with patch.object(h.bus,'write_i2c_block_data',side_effect=OSError('disconnected')):
   with self.assertRaises(OSError):h.oled_image(render_page('clock',{},{}))
 def test_all_pages(self):
  for page in app.validate({})['oled_pages']+['custom','cpu','ram','bandwidth','raid']:
   self.assertEqual(render_page(page,{'disks':[]},{},(1,1)).size,(128,64))
if __name__=='__main__':unittest.main()
