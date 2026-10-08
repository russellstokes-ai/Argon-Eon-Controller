import glob, json, os, socket, subprocess, time, urllib.request
from datetime import timedelta
from reliability import button_action

STANDALONE = not os.environ.get('SUPERVISOR_TOKEN')  # true when not running as a Home Assistant app

def supervisor(path,body=None):
 if STANDALONE: return {}  # no Supervisor to talk to; callers already tolerate an empty/missing result
 req=urllib.request.Request('http://supervisor'+path,
  data=None if body is None else json.dumps(body).encode(),
  headers={'Authorization':'Bearer '+os.environ.get('SUPERVISOR_TOKEN',''),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=5) as r: result=json.load(r)
 if isinstance(result,dict) and result.get('result')=='error': raise RuntimeError(result.get('message','Supervisor request failed'))
 return result

def buttons_once(stop,callback,report):
 try:
  import gpiod
  from gpiod.line import Direction,Edge,Bias,Clock
  candidates=[]
  for path in glob.glob('/dev/gpiochip*'):
   with gpiod.Chip(path) as chip:
    info=chip.get_info()
    if info.label=='pinctrl-bcm2711' and info.num_lines>=5: candidates.append(path)
  if len(candidates)!=1: raise RuntimeError('Expected one Pi 4 pinctrl-bcm2711 GPIO controller')
  settings=gpiod.LineSettings(direction=Direction.INPUT,edge_detection=Edge.BOTH,bias=Bias.PULL_DOWN,event_clock=Clock.MONOTONIC)
  with gpiod.request_lines(candidates[0],consumer='argon-eon-controls',config={4:settings}) as lines:
   report('Monitoring GPIO4'); rise=None; sequence=None; last=0
   while not stop.is_set():
    if not lines.wait_edge_events(timedelta(seconds=1)): continue
    for event in lines.read_edge_events():
     contiguous=sequence is None or event.line_seqno==sequence+1
     sequence=event.line_seqno
     if not contiguous: rise=None
     if event.event_type==gpiod.EdgeEvent.Type.RISING_EDGE: rise=event.timestamp_ns
     elif rise is not None:
      width=(event.timestamp_ns-rise)/1e6; rise=None
      action=button_action(width)
      if action and time.monotonic()-last>=2:
       last=time.monotonic(); callback(action,width)
 except Exception as e: report('Unavailable: '+str(e))

def buttons(stop,callback,report):
 while not stop.is_set():
  buttons_once(stop,callback,report)   # returns after reporting an error (or when stopping)
  stop.wait(30)                        # retry: the GPIO controller may appear late or a transient fault may clear

def reboot():
 """Reboot the host, whichever way this instance can: the Supervisor API in Home Assistant,
 or systemctl directly when running standalone (the systemd unit must run as root)."""
 if not STANDALONE: return supervisor('/host/reboot',{'force':False})
 subprocess.run(['systemctl','reboot'],check=True,timeout=10)

def local_ip():
 """Best-effort LAN address for the OLED network page when there is no Supervisor to ask.
 Opens no connection: UDP connect() only selects the outbound interface/address locally."""
 try:
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
   s.connect(('8.8.8.8',80)); return s.getsockname()[0]
 except OSError:
  return None

def poweroff():
 if not STANDALONE: return supervisor('/host/shutdown',{'force':False})
 subprocess.run(['systemctl','poweroff'],check=True,timeout=10)

def local_info():
 """hostname/OS/kernel for the OLED network page and diagnostics when there is no Supervisor to ask."""
 import platform
 os_name='Linux'
 try:
  for line in open('/etc/os-release'):
   if line.startswith('PRETTY_NAME='): os_name=line.split('=',1)[1].strip().strip('"'); break
 except OSError: pass
 return {'hostname':platform.node(),'operating_system':os_name,'kernel':platform.release(),'chassis':'embedded'}
