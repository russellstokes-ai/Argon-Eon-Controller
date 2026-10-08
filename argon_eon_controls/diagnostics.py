from pathlib import Path

def usb_devices():
 result=[]
 for p in Path('/sys/bus/usb/devices').glob('*'):
  if not (p/'idVendor').exists(): continue
  def read(k):
   try: return (p/k).read_text().strip()
   except OSError: return None
  drivers=[]
  for interface in p.glob(p.name+':*'):
   if (interface/'driver').exists(): drivers.append((interface/'driver').resolve().name)
  result.append(dict(port=p.name,vendor=read('idVendor'),product_id=read('idProduct'),product=read('product'),revision=read('bcdDevice'),speed_mbps=read('speed'),drivers=drivers))
 return result

def metrics():
 import psutil
 mem=psutil.virtual_memory(); swap=psutil.swap_memory()
 out={'cpu_percent':psutil.cpu_percent(), 'memory_percent':mem.percent,'swap_used':swap.used}
 io=psutil.disk_io_counters()
 try: out['uptime_seconds']=int(__import__('time').time()-psutil.boot_time())
 except Exception: pass
 out['disk_bytes']={'read':io.read_bytes,'write':io.write_bytes} if io else {}
 try: out['raid']=Path('/proc/mdstat').read_text()[:2048]
 except OSError: out['raid']='Unavailable'
 return out
