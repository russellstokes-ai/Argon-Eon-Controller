import re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'static'/'app.js').read_text(); HTML=(ROOT/'templates'/'index.html').read_text(); CSS=(ROOT/'static'/'style.css').read_text()

class StatusStates(unittest.TestCase):
 def test_three_states_exist_in_script_and_styles(self):
  for state in ('ok','lost','error'):
   self.assertIn("setState('%s'"%state,JS); self.assertIn('#badge.%s'%state,CSS)
 def test_connection_failures_and_page_errors_are_reported_separately(self):
  self.assertIn("setState('lost'",JS.split('latest=data')[0])     # network failure handled before any drawing
  self.assertIn("setState('error'",JS.split('latest=data')[1])    # drawing failures handled after it
 def test_each_section_draws_in_its_own_try_block(self):
  self.assertRegex(JS,r"(?s)for\(let step of \[.*\]\)\{\s*try\{step\(\)\}catch")
 def test_error_banner_exists_and_starts_hidden(self):
  self.assertRegex(HTML,r'id="appError"[^>]*hidden')

class UnsavedChanges(unittest.TestCase):
 def test_footer_has_marker_and_message_area(self):
  self.assertRegex(HTML,r'id="saveState" hidden'); self.assertIn('id="message"',HTML)
 def test_save_clears_the_marker_and_messages_expire(self):
  self.assertRegex(JS,r"await post\('config',c\);cfg=c;setDirty\(false\);msg\('Settings saved','ok'\)")
  self.assertIn('setTimeout(()=>{m.textContent=',JS)
 def test_changes_to_settings_curves_pages_and_drive_types_mark_the_page_dirty(self):
  for scope in ('[data-setting]','#cpu_curve input','#disk_curve input','#pages input','#drives select'): self.assertIn(scope,JS)
  self.assertIn('setDirty(true)};row.append(b)',JS)     # moving a page up/down

class DiagnosticsTab(unittest.TestCase):
 def test_usb_is_a_collapsible_table_and_events_a_list(self):
  self.assertRegex(HTML,r'<details class="usbbox">.*<table id="usb">'); self.assertIn('<ol id="events"',HTML)
 def test_events_are_sorted_newest_first(self):
  self.assertIn('.sort((a,b)=>b.time-a.time)',JS)
 def test_no_raw_json_dumps_remain_on_the_page(self):
  self.assertNotIn('JSON.stringify(latest.',JS); self.assertNotIn('<pre',HTML)
 def test_about_card_shows_the_version(self):
  self.assertRegex(HTML,r'class="card about".*v\{\{ version \}\}')

if __name__=='__main__': unittest.main()
