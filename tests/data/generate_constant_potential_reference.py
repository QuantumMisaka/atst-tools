"""Regenerate the upstream FCP trace with a deterministic, non-computing backend.

Usage: python generate_constant_potential_reference.py /path/to/FCPelectrochem.py
Requires the pinned upstream source (SHA verified) and its pandas dependency.
This does not execute ABACUS or modify an ASE installation.
"""
from pathlib import Path
import hashlib,importlib.util,json,sys,types,tempfile
import numpy as np
from ase import Atoms
from ase.calculators.calculator import Calculator,all_changes

trace=[]
class Abacus(Calculator):
 name='abacus'
 implemented_properties=['energy','free_energy','forces','stress']
 def __init__(self,profile=None,directory='.',**parameters):
  super().__init__(directory=directory,**parameters);self.profile=profile or object()
 def calculate(self,atoms=None,properties=('energy',),system_changes=all_changes):
  super().calculate(atoms,properties,system_changes)
  n=float(self.parameters['nelec']);x=n-10;ef=5+.4*x+.02*x**3
  energy=100+5*x+.2*x*x+.005*x**4
  self.results.update(energy=energy,free_energy=energy,forces=np.zeros((len(atoms),3)),stress=np.zeros(6),efermi=ef)
  out=Path(self.directory)/'OUT.ABACUS';out.mkdir(parents=True,exist_ok=True)
  (out/'running_scf.log').write_text('The vacuum level is 10.0 eV\n')
  trace.append({'nelec':n,'efermi':ef,'mu':ef-10,'raw_energy':energy})
 def get_fermi_level(self):return self.results['efermi']
module=types.ModuleType('ase.calculators.abacus');module.Abacus=Abacus
sys.modules['ase.calculators.abacus']=module
source=Path(sys.argv[1])
assert hashlib.sha256(source.read_bytes()).hexdigest() == 'bd1cbf41abf34d68a41f6f1579275e6c082e8f0f8be09c2d629153c2aa745040', 'Unexpected upstream FCP source'
spec=importlib.util.spec_from_file_location('fcp_reference',source);ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
runs=[]
for always in (False,True):
 trace.clear()
 with tempfile.TemporaryDirectory(prefix='fcp-reference-') as d:
  atoms=Atoms('H',positions=[[0,0,0]],cell=[10,10,20],pbc=True)
  calc=ref.FCP(innercalc=Abacus(directory=d,nelec=8),fcptxt=str(Path(d)/'full.log'),U=.4,NELECT=8,NELECT0=10,C=.002,work_ref=4.6,adaptive_lr=False,FCPconv=1e-5,max_FCP_iter=100,always_adjust=always)
  calc.directory=d
  atoms.calc=calc;energy=atoms.get_potential_energy()
  runs.append({'always_adjust':always,'trace':list(trace),'published_energy':energy,'last_evaluated_nelec':trace[-1]['nelec'],'next_guess_nelec':calc.Nelect,'text_log':(Path(d)/'tmp-log-FCP.txt').read_text()})
result={'reference_revision':'9f96cacb6b69cb39aeb180e73f415f806e16a75e','reference_path':'version2/FCPelectrochem.py','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'backend':'x=N-10; EF=5+0.4*x+0.02*x^3; Vvac=10; A=100+5*x+0.2*x^2+0.005*x^4; forces=0','parameters':{'initial_electrons':8,'reference_electrons':10,'potential_v':.4,'work_ref':4.6,'capacitance_initial':.002,'capacitance_unit':'e/(V Angstrom^2)','potential_tolerance_v':1e-5,'max_iterations':100},'cell':[10,10,20],'runs':runs}
dest=Path(__file__).with_name('constant_potential_reference.json');dest.parent.mkdir(exist_ok=True,parents=True);dest.write_text(json.dumps(result,indent=2)+'\n')
print([(r['always_adjust'],len(r['trace']),r['published_energy'],r['last_evaluated_nelec'],r['next_guess_nelec']) for r in runs])
