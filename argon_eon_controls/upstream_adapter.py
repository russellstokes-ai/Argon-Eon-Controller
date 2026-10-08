"""Execute selected pinned upstream functions without installer/module side effects."""
import ast, hashlib
from pathlib import Path
ROOT=Path(__file__).parent/'upstream_argoneon'

def functions(filename,names,namespace):
 import json
 raw=(ROOT/filename).read_bytes()
 expected=json.loads((ROOT/'sha256.json').read_text())[filename]
 if hashlib.sha256(raw).hexdigest()!=expected: raise RuntimeError('Upstream source checksum mismatch')
 tree=ast.parse(raw.decode('utf-8-sig'))
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 if {n.name for n in nodes}!=set(names): raise RuntimeError('Upstream functions changed')
 # Original OLED helpers silently discard I/O errors. Propagate them into diagnostics.
 class Errors(ast.NodeTransformer):
  def visit_ExceptHandler(self,node):
   node.body=[ast.Raise()]; return node
 tree=ast.Module(body=nodes,type_ignores=[])
 tree=Errors().visit(tree); ast.fix_missing_locations(tree)
 exec(compile(tree,str(ROOT/filename),'exec'),namespace)
 return namespace

def oled(bus):
 names=['oled_power','oled_reset','oled_flushblock']
 return functions('argoneonoled.py',names,dict(bus=bus,ADDR_OLED=0x3c,OLED_SLAVEADDRESS=0x6a,
  OLED_WD=128,OLED_HT=64,oled_imagebuffer=[0]*1024))
