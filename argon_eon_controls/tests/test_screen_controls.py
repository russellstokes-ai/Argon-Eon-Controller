import os,sys,tempfile,unittest
from pathlib import Path
os.environ.setdefault('EON_DATA',tempfile.mkdtemp())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from reliability import PAGES
class ScreenControls(unittest.TestCase):
 def setUp(self): app.app.testing=True;self.c=app.app.test_client();self.h={'X-Eon-Request':'1'}
 def test_every_page_previews_as_png(self):
  for p in sorted(PAGES):
   r=self.c.get('/api/oled/preview/%s.png'%p);self.assertEqual(r.status_code,200,p);self.assertEqual(r.mimetype,'image/png');self.assertTrue(r.data.startswith(b'\x89PNG'))
 def test_unknown_page_is_404(self): self.assertEqual(self.c.get('/api/oled/preview/nope.png').status_code,404)
 def test_next_page_wakes_display(self):
  app.page_wake.clear();r=self.c.post('/api/oled/next',json={},headers=self.h);self.assertEqual(r.status_code,200);self.assertTrue(app.page_wake.is_set());app.page_wake.clear()
 def test_test_button_endpoint_still_works(self):
  app.page_wake.clear();self.assertEqual(self.c.post('/api/oled/test',json={},headers=self.h).status_code,200);self.assertTrue(app.page_wake.is_set());app.page_wake.clear()
 def test_next_requires_request_header(self):
  self.assertNotEqual(self.c.post('/api/oled/next',json={}).status_code,200)
if __name__=='__main__':unittest.main()
