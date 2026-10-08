import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hardware
class I2CMessage(unittest.TestCase):
 def open_with(self,exc):
  with patch.object(hardware,'SMBus',side_effect=exc): return hardware.EonHardware()
 def test_missing_device_says_how_to_fix_it(self):
  h=self.open_with(FileNotFoundError(2,'No such file or directory'));self.assertIn('enable I2C',h.error);self.assertIsNone(h.bus)
  with self.assertRaises(RuntimeError) as cm: h.set_fan(50)
  self.assertIn('/dev/i2c-1',str(cm.exception))
 def test_permission_message_mentions_protection_mode(self):
  self.assertIn('Protection mode',self.open_with(PermissionError(13,'denied')).error)
 def test_other_errors_pass_through(self):
  self.assertEqual(self.open_with(OSError('boom')).error,'boom')
if __name__=='__main__':unittest.main()
