import copy, datetime as dt, fcntl, json, logging, os, queue, signal, threading, time
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template, abort
from reliability import DEFAULTS, validate, atomic_save, Cooling
from hardware import EonHardware,cpu_temp,render_page
from entities import drive_entities
from storage import DiskMonitor,inventory,smart_event
from host import supervisor,buttons,reboot,poweroff,local_ip,local_info,STANDALONE
from diagnostics import usb_devices,metrics
VERSION='1.0.2'
app=Flask(__name__); app.config['MAX_CONTENT_LENGTH']=32768
DATA=Path(os.getenv('EON_DATA','/data')); DATA.mkdir(parents=True,exist_ok=True)
lock=threading.RLock(); stop=threading.Event(); jobs=queue.Queue(maxsize=16)
state={'status':'Starting','fan':None,'disks':[],'events':[],'commissioned':True,'button':'Starting'}
heartbeat=0.; override=(None,0.); page_index=0; page_wake=threading.Event(); hw=None
wake_now=threading.Event(); WATCH_SECONDS=10
workers=[]; save_lock=threading.Lock()
cfg=copy.deepcopy(DEFAULTS)
try:
 saved=json.loads((DATA/'settings.json').read_text())
 cfg=validate({k:v for k,v in saved.items() if k in DEFAULTS})
except FileNotFoundError: pass
except Exception as e: state['config_error']='Invalid saved settings; conservative defaults loaded: '+str(e)
# Commissioning is intentionally repeated per process start; do not trust stale hardware identity.

def event(message):
 logging.warning(message)
 with lock:
  state['events']=(state['events']+[{'time':time.time(),'message':message}])[-50:]

def snap():
 with lock: return copy.deepcopy(state)

def configuration():
 with lock: return copy.deepcopy(cfg)

def drive_type(name):
 """Effective SMART bridge type: the user's choice, else the automatic type found for this disk."""
 kind=configuration()['drive_types'].get(name)
 if kind: return kind
 return next((d.get('bridge_type') for d in snap()['disks'] if d.get('name')==name),None)

@app.before_request
def ingress():
 # No host port exposed. Only the Supervisor ingress proxy may administer hardware.
 if not app.testing and not STANDALONE and request.remote_addr!='172.30.32.2': abort(403)
 if request.method=='POST' and request.headers.get('X-Eon-Request')!='1': abort(403)

@app.errorhandler(ValueError)
def bad(e): return jsonify(error=str(e)),400

@app.get('/')
def index(): return render_template('index.html',version=VERSION)
@app.get('/health')
def health():
 return ('ok',200) if heartbeat and time.monotonic()-heartbeat<25 and all(t.is_alive() for t in workers) else ('A control worker is not healthy',503)
@app.get('/api/status')
def status():
 s=snap(); s.update(config=configuration(),version=VERSION); return jsonify(s)
@app.post('/api/config')
def settings():
 global cfg
 try: candidate=validate(request.get_json())
 except (ValueError,TypeError,KeyError) as e: raise ValueError(str(e))
 with save_lock: atomic_save(DATA/'settings.json',candidate)  # outside the state lock: a slow disk write must never stall cooling
 with lock: previous=cfg['drive_types']; cfg=candidate
 if candidate['drive_types']!=previous: wake_now.set()   # a changed drive setting is applied now, not at the next 5-minute check
 return jsonify(ok=True)
@app.get('/api/config/export')
def export(): return app.response_class(json.dumps(configuration(),indent=2),mimetype='application/json',headers={'Content-Disposition':'attachment; filename=eon-settings.json'})
@app.get('/api/diagnostics')
def diagnostics():
 s=snap(); s.update(version=VERSION,config=configuration(),cooling_age=time.monotonic()-heartbeat)
 # No tokens, environment dump, drive serials or raw system logs.
 return app.response_class(json.dumps(s,indent=2),mimetype='application/json',headers={'Content-Disposition':'attachment; filename=eon-diagnostics.json'})
@app.post('/api/fan')
def testfan():
 global override
 speed=request.get_json().get('speed')
 if type(speed) is not int or not 0<=speed<=100: raise ValueError('Speed must be 0–100')
 with lock:
  override=(speed,time.monotonic()+10)
 return jsonify(ok=True,reverts_in=10)
@app.post('/api/oled/test')
def testdisplay():
 global page_index
 page_index=configuration()['oled_pages'].index('custom') if 'custom' in configuration()['oled_pages'] else 0
 page_wake.set(); return jsonify(ok=True)
@app.post('/api/oled/next')
def nextdisplay():
 page_wake.set(); return jsonify(ok=True)
@app.post('/api/oled/pattern/<name>')
def patterndisplay(name):
 if name not in ('white','black','checker','rings'): abort(404)
 with lock: state['test_pattern']=name
 page_wake.set(); return jsonify(ok=True)
@app.post('/api/disks/recheck')
def recheckdisks():
 wake_now.set(); return jsonify(ok=True)
def display_state():
 s=snap(); s['hostname']=s.get('host',{}).get('hostname') or 'Home Assistant'; s['ip']=s.get('host_ip','See HA network settings')
 s['max_disk_temp']=max([d['temperature'] for d in s['disks'] if d.get('temperature') is not None]+[0]) or None
 return s
@app.get('/api/oled/preview/<page>.png')
def previewdisplay(page):
 import io
 from PIL import Image
 if page in ('white','black','checker','rings'):
  from hardware import test_pattern
  image=test_pattern(page).resize((384,192),Image.NEAREST)
  buf=io.BytesIO(); image.save(buf,'PNG'); r=app.response_class(buf.getvalue(),mimetype='image/png'); r.headers['Cache-Control']='no-store'; return r
 from reliability import PAGES
 if page not in PAGES: abort(404)
 image=render_page(page,display_state(),configuration(),(0,0)).convert('L').point(lambda v:255 if v else 0).resize((384,192),Image.NEAREST)
 buf=io.BytesIO(); image.save(buf,'PNG'); r=app.response_class(buf.getvalue(),mimetype='image/png'); r.headers['Cache-Control']='no-store'; return r
@app.post('/api/rtc/sync')
def rtcsync():
 try: jobs.put_nowait(('rtc',None,None))
 except queue.Full: raise ValueError('Maintenance queue is full')
 return jsonify(queued=True)

@app.post('/api/smart/test')
def smarttest():
 b=request.get_json(); c=configuration(); name=b.get('name')
 disk=next((d for d in snap()['disks'] if d['name']==name),None)
 if disk is None or disk.get('power')=='No media' or drive_type(name) in (None,'ignore'): raise ValueError('Configure an existing disk first')
 if b.get('test') not in ('short','long'): raise ValueError('Invalid test')
 try: jobs.put_nowait(('smart',name,b['test']))
 except queue.Full: raise ValueError('A maintenance queue is full')
 return jsonify(queued=True)

def cooling():
 global heartbeat
 policy=Cooling(); next_cpu=0.; cpu=None; lastwrite=0.; last_command=None
 while not stop.is_set():
  now=time.monotonic(); c=configuration()
  if now>=next_cpu:
   cpu=cpu_temp(); next_cpu=now+10
   if cpu is not None and not 0<cpu<120: cpu=None
  with lock:
   s=copy.deepcopy(state); manual,until=override
  desired,reason=policy.target(c,cpu,s['disks'],now,manual if now<until else None,s['commissioned'])
  try:
   if last_command!=desired or now-lastwrite>=10:
    actual=hw.set_fan(desired); last_command=actual; lastwrite=now
   with lock: state.update(fan=last_command,cpu_temp=cpu,status='Control active',reason=reason,fan_error=None,updated=time.time())
  except Exception as e:
   last_command=None
   with lock: state.update(fan=None,cpu_temp=cpu,status='Fan command failed',fan_error=str(e),reason=reason)
  heartbeat=time.monotonic()
  stop.wait(1)
 # Only cooling worker owns fan writes, including normal termination.
 try: hw.set_fan(100)
 except Exception as e: event('Could not apply shutdown fan command: '+str(e))

def disks_worker():
 monitor=DiskMonitor(); due=0.; known=set(); stamps={}; alerted={}
 try: stamps=json.loads((DATA/'maintenance.json').read_text())
 except Exception: pass
 while not stop.is_set():
  c=configuration()
  if time.monotonic()>=due or wake_now.is_set():
   wake_now.clear(); started=time.monotonic()
   try:
    rows=monitor.poll(c['drive_types']); names={d['name'] for d in rows}
    known=names
    with lock: state['disks']=rows; state['disk_checked']=time.time(); state['disk_error']=None
    for d in rows:
     message=smart_event(d,alerted)
     if message: event(message)
    now=dt.datetime.now(ZoneInfo(c['timezone']))
    period=now.strftime('%G-W%V') if c['smart_schedule']=='weekly' else now.strftime('%Y-%m')
    if c['smart_schedule']!='disabled':
     for d in rows:
      key=d['identity']+'|'+c['smart_schedule']+'|'+c['smart_test']
      if d['power']=='Active' and stamps.get(key)!=period:
       # Mark before command to avoid duplicate test starts after process/power failure.
       stamps[key]=period; atomic_save(DATA/'maintenance.json',stamps)
       r=monitor.test(d['name'],d['bridge_type'],c['smart_test'])
       if r['status']=='deferred': stamps.pop(key,None); atomic_save(DATA/'maintenance.json',stamps)
       event('Scheduled SMART '+d['name']+': '+r['status'])
   except Exception as e:
    with lock: state['disk_error']=str(e)
   due=started+300  # scheduled from poll start so every sample stays inside the freshness window
  try:
   job=jobs.get(timeout=1)
   if job[0]=='rtc':
    now=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    if not 2024<=now.year<=2099: raise ValueError('Host time is implausible')
    from upstream_adapter import functions
    ns=functions('argoneond.py',['numDECtoBCD','setRTCdatetime'],
       {'bus':hw.bus,'ADDR_RTC':0x51,'math':__import__('math'),'getLocaltimeOffset':lambda:dt.timedelta(0)})
    if hw.bus is None: raise ValueError('I2C unavailable')
    with hw.lock:
     ns['setRTCdatetime'](now)
     actual=hw.rtc_status()
    if not actual.get('clock_valid'): raise RuntimeError('RTC reports invalid clock after write')
    readback=dt.datetime.fromisoformat(actual['time'])
    if abs((readback-now).total_seconds())>3: raise RuntimeError('RTC readback mismatch')
    with lock: state['rtc']=actual
    event('RTC UTC time written and read back; host clock unchanged')
    continue
   _,name,kind=job
   if name not in [d['name'] for d in inventory()]: raise ValueError('Disk no longer present')
   bridge=drive_type(name)
   if bridge in (None,'ignore'): raise ValueError('No SMART bridge type for this disk')
   result=monitor.test(name,bridge,kind)
   event('SMART '+name+': '+result['status'])
  except queue.Empty: pass
  except Exception as e: event('SMART test failed: '+str(e))

def watch_worker():
 """Cheap sysfs-only watch: reports vanished/new disks within seconds and asks for one immediate
 SMART poll when a sleeping disk is touched by the OS. Never talks to a disk itself."""
 import presence
 previous=presence.snapshot(); last=None  # None, not 0: monotonic() can be < 30 s just after boot
 while not stop.wait(WATCH_SECONDS):
  try:
   current=presence.snapshot()
   stamp=dt.datetime.now(ZoneInfo(configuration()['timezone'])).strftime('%d %b %H:%M:%S')
   gone=presence.disappeared(previous,current); new=presence.appeared(previous,current)
   for name in gone: event('Disk disappeared: '+presence.describe(previous[name])+' at '+stamp)
   for name in new: event('Disk appeared: '+presence.describe(current[name])+' at '+stamp)
   with lock: rows={d['identity']:d for d in state['disks'] if d.get('identity')}
   asleep=[n for n in presence.woken(previous,current) if rows.get(n,{}).get('power')=='Standby']
   with lock: state['present']=sorted(v['name'] for v in current.values()); state['watch_error']=None
   if gone or new or (asleep and (last is None or time.monotonic()-last>=30)):
    if asleep: last=time.monotonic()
    before=snap().get('disk_checked'); wake_now.set()
    for _ in range(60):
     if stop.wait(1) or snap().get('disk_checked')!=before: break
    after=presence.snapshot()  # re-baseline I/O counters only, so the poll can never re-trigger the watch;
    current={n:(dict(v,io=after[n]['io']) if n in after else v) for n,v in current.items()}  # membership changes stay visible next loop
   previous=current
  except Exception as e:
   with lock: state['watch_error']=str(e)

def display_worker():
 global page_index
 from PIL import Image
 lastrest=time.monotonic(); previous=0.; cached=None; resting_until=0.; lastactive=time.monotonic(); pattern_since=[0.]; cached_pattern=[None]
 while not stop.is_set():
  c=configuration(); now=time.monotonic(); s=snap()
  try:
   local=dt.datetime.now(ZoneInfo(c['timezone'])); clock=local.strftime('%H:%M')
   start,end=c['night_start'],c['night_end']
   night=c['night_enabled'] and (start<=clock<end if start<end else clock>=start or clock<end)
   if c['burnin_enabled'] and now-lastrest>=c['burnin_rest_minutes']*60:
    resting_until=now+c['burnin_rest_seconds']; lastrest=now
   wake=page_wake.is_set(); page_wake.clear()
   if wake: previous=0.; resting_until=0.; lastactive=now
   saver=c['screensaver_seconds'] and now-lastactive>=c['screensaver_seconds']
   pattern=s.get('test_pattern')
   if pattern:
    if pattern!=cached_pattern[0]: pattern_since[0]=now; cached_pattern[0]=pattern
    from hardware import test_pattern
    hw.oled_brightness(c['brightness']); hw.oled_image(test_pattern(pattern)); cached='on'; previous=now
    if now-pattern_since[0]>=10:
     with lock: state['test_pattern']=None
     cached_pattern[0]=None
   elif not c['oled_enabled'] or night or now<resting_until or saver:
    if cached!='off': hw.oled_power(False); cached='off'
   elif now-previous>=c['page_seconds'] or cached=='off':
    s['hostname']=s.get('host',{}).get('hostname','Home Assistant')
    s['ip']=s.get('host_ip','See HA network settings')
    s['max_disk_temp']=max([d['temperature'] for d in s['disks'] if d.get('temperature') is not None]+[0]) or None
    shift=[(0,0),(1,0),(1,1),(0,1)][page_index%4] if c['burnin_enabled'] else (0,0)
    hw.oled_brightness(c['brightness'])
    hw.oled_image(render_page(c['oled_pages'][page_index%len(c['oled_pages'])],s,c,shift))
    page_index+=1; previous=now; cached='on'
   with lock: state['oled_error']=None
  except Exception as e:
   with lock: state['oled_error']=str(e)
  stop.wait(1)

def onbutton(action,width):
 global page_index
 event(f'Button pulse {width:.1f} ms: {action}')
 if action=='page': page_wake.set(); return
 c=configuration()
 if not c['button_actions']: return
 if action=='reboot' and not c['button_reboot']: return
 try: (poweroff() if action=='shutdown' else reboot())
 except Exception as e: event('Host request failed: '+str(e))

def telemetry():
 notified={}; published={}; host_due=0.  # hostname/OS/kernel/IP barely ever change: refetch every 15 min, not every 30s
 while not stop.is_set():
  s=snap(); c=configuration(); entity_error=None
  try:
   with lock: state['usb']=usb_devices(); state['metrics']=metrics()
   try:
    rtc=hw.rtc_status()
    with lock: state['rtc']=rtc
   except Exception: pass
   if time.monotonic()>=host_due:
    host_due=time.monotonic()+900
    host=local_info() if STANDALONE else supervisor('/host/info').get('data',{})
    with lock: state['host']={k:host.get(k) for k in ('hostname','operating_system','kernel','chassis')}
    try:
     if STANDALONE:
      ip=local_ip()
      if ip:
       with lock: state['host_ip']=ip
     else:
      for i in supervisor('/network/info').get('data',{}).get('interfaces',[]):
       addr=(i.get('ipv4') or {}).get('address') or []
       if i.get('primary') and addr:
        with lock: state['host_ip']=addr[0].split('/')[0]
        break
    except Exception: pass
   if c['publish_entities']:
    for name,value,unit in [('cpu_temperature',s.get('cpu_temp'),'°C'),('fan_command',s.get('fan'),'%')]:
     supervisor('/core/api/states/sensor.argon_eon_'+name,{'state':value if value is not None else 'unavailable','attributes':{'friendly_name':'Argon EON '+name.replace('_',' '),'unit_of_measurement':unit}})
    try:   # drive sensors never block the cpu/fan sensors above or the notifications below
     current={}
     for eid,value,attrs in drive_entities(s.get('disks',[])):
      supervisor('/core/api/states/'+eid,{'state':value,'attributes':attrs}); current[eid]=attrs.get('friendly_name')
     for eid,fname in published.items():
      if eid not in current: supervisor('/core/api/states/'+eid,{'state':'unavailable','attributes':{'friendly_name':fname}})
     published.clear(); published.update(current)
    except Exception as e: entity_error=str(e)
   standing=[m for m in [s.get('fan_error'),s.get('config_error'),s.get('disk_error'),s.get('reason') if s.get('reason')=='Emergency temperature' else None,'Protection mode is ON for Argon EON Controls: turn it off on the app Info tab and restart it' if s.get('protected') else None] if m]
   occurrences=[e['message'] for e in s['events'] if 'failed' in e['message'].lower() or 'disappeared' in e['message'] or e['message'].startswith('SMART ')]
   if c['notifications']:
    from alerts import sync,notification_id
    sync(notified,standing,occurrences,
     lambda m: supervisor('/core/api/services/persistent_notification/create',{'title':'Argon EON Controls','message':m,'notification_id':notification_id(m)}),
     lambda m: supervisor('/core/api/services/persistent_notification/dismiss',{'notification_id':notification_id(m)}))
   with lock: state['ha_error']=entity_error
  except Exception as e:
   with lock: state['ha_error']=str(e)
  stop.wait(30)

def guarded(f):
 """Run a worker forever: an unexpected exception is logged and the worker restarted, never left dead."""
 def run():
  while not stop.is_set():
   try: return f()
   except Exception as e:
    logging.exception('%s crashed; restarting',f.__name__); event(f'{f.__name__} restarted after error: {e}'); stop.wait(5)
 return run
def main():
 global hw
 logging.basicConfig(level=logging.INFO)
 instance=(DATA/'controller.lock').open('w')
 fcntl.flock(instance,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try: protected=False if STANDALONE else supervisor('/addons/self/info').get('data',{}).get('protected')
 except Exception: protected=None
 with lock: state['protected']=protected
 if protected: event('Protection mode is ON: turn it off (app Info tab) and restart, or I2C, GPIO, the fan and the screen cannot work')
 try:
  if not protected and configuration()['auto_i2c']:
   from i2c_setup import ensure
   report=[]
   try: result=ensure(DATA/'i2c_attempted',report=report,standalone=STANDALONE)
   finally:
    with lock: state['i2c_report']=report
   if result=='reboot':
    event('I2C enabled in the Pi boot config; requesting one host reboot to activate it'); reboot()
 except Exception as e: event('I2C auto-enable skipped: '+str(e))
 hw=EonHardware()
 # Finite adapter timeout/retries where supported; never force access to a kernel-owned address.
 if hw.bus:
  try: fcntl.ioctl(hw.bus.fd,0x0702,20); fcntl.ioctl(hw.bus.fd,0x0701,1)
  except OSError: pass
 def report(s):
  with lock: state['button']=s
 threads=[threading.Thread(target=guarded(f),daemon=True,name=f.__name__) for f in (cooling,disks_worker,display_worker,telemetry,watch_worker)]
 threads.append(threading.Thread(target=buttons,args=(stop,onbutton,report),daemon=True))
 workers.extend(threads)
 for t in threads: t.start()
 def terminate(*_): stop.set()
 signal.signal(signal.SIGTERM,terminate); signal.signal(signal.SIGINT,terminate)
 from waitress import create_server
 server=create_server(app,host='0.0.0.0',port=8099,threads=4)
 threading.Thread(target=server.run,daemon=True).start()
 stop.wait()
 threads[0].join(timeout=5)
 server.close()
if __name__=='__main__': main()
