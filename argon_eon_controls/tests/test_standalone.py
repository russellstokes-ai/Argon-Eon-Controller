import importlib,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

class HostModeSwitch(unittest.TestCase):
 def load(self,token):
  env=dict(os.environ)
  if token is None: env.pop('SUPERVISOR_TOKEN',None)
  else: env['SUPERVISOR_TOKEN']=token
  with patch.dict(os.environ,env,clear=True):
   import host; return importlib.reload(host)
 def test_no_token_is_standalone(self):
  h=self.load(None);self.assertTrue(h.STANDALONE);self.assertEqual(h.supervisor('/anything'),{})
 def test_token_present_is_ha_mode(self):
  h=self.load('x');self.assertFalse(h.STANDALONE)
 def test_standalone_reboot_uses_systemctl(self):
  h=self.load(None)
  with patch('subprocess.run') as run:
   h.reboot();run.assert_called_once_with(['systemctl','reboot'],check=True,timeout=10)
 def test_standalone_poweroff_uses_systemctl(self):
  h=self.load(None)
  with patch('subprocess.run') as run:
   h.poweroff();run.assert_called_once_with(['systemctl','poweroff'],check=True,timeout=10)
 def test_ha_mode_reboot_goes_through_supervisor(self):
  h=self.load('x')
  with patch.object(h,'supervisor') as call:
   h.reboot();call.assert_called_once_with('/host/reboot',{'force':False})
 def test_local_ip_returns_a_string_or_none(self):
  h=self.load(None); ip=h.local_ip(); self.assertTrue(ip is None or isinstance(ip,str))
 def test_local_info_has_expected_keys(self):
  h=self.load(None); info=h.local_info()
  for k in ('hostname','operating_system','kernel','chassis'): self.assertIn(k,info)

class I2CStandalone(unittest.TestCase):
 def test_standalone_writes_boot_config_directly_no_mount(self):
  import i2c_setup
  tmp=Path(tempfile.mkdtemp());boot=tmp/'boot-firmware';boot.mkdir();(boot/'config.txt').write_text('a=1\n')
  mk=tmp/'marker'
  with patch('i2c_setup.BOOT_CANDIDATES',(str(boot),)), patch('subprocess.run',side_effect=AssertionError('must not mount anything standalone')):
   self.assertEqual(i2c_setup.ensure(mk,device=tmp/'no-i2c',standalone=True),'reboot')
  self.assertIn('dtparam=i2c_arm=on',(boot/'config.txt').read_text());self.assertTrue(mk.exists())
 def test_standalone_no_boot_partition_raises_actionable_message(self):
  import i2c_setup
  tmp=Path(tempfile.mkdtemp())
  with patch('i2c_setup.BOOT_CANDIDATES',(str(tmp/'nope1'),str(tmp/'nope2'))):
   with self.assertRaises(RuntimeError) as cm:
    i2c_setup.ensure(tmp/'marker',device=tmp/'no-such-i2c-device',standalone=True)
  self.assertIn('raspi-config',str(cm.exception))

if __name__=='__main__':unittest.main()
