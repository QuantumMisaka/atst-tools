# ATST-Tools
Advanced ASE Transition State Tools for ABACUS and Deep-Potential, including:
- NEB, including CI-NEB, IT-NEB and others.
- Serial Dynamic NEB (DyNEB) calculation.
- AutoNEB: an automatic NEB workflow.
- Single-End TS search: Sella, Dimer.
- IRC analysis by Sella.
- Double-to-single (D2S) TS workflow: neb2dimer, neb2sella.
- Vibration analysis and ideal gas thermochemistry analysis.

Version 1.5.0

Copyright @ QuantumMisaka from TMC-PKU & AISI

## Update log from 1.4.0 to 1.5.0
- Add internal reaction coordination (IRC) calculation by using Sella packages.
- Add *neb2dimer_dp.py*, *neb2sella_dp.py*, *relax_dp.py* for deepmd usage, including tf and torch version, and all D2S method are using pymatgen IDPP.
- Change default relaxation optimizer from BFGS to QuasiNewton (BFGSLineSearch).
- change the way to use `AbacusProfile` to march the newest version of ase-abacus interface, which use different command format.
- Since constraints read-in problem in ASE-ABACUS interface is fixed [#28](https://gitlab.com/1041176461/ase-abacus/-/issues/28), the constraints is the two scripts above is modified, make Dimer and Sella useful.
- Single-End TS search scripts update using Dimer method and Sella packages.
- Default *neb_make.py* change to pymatgen version below.
- *neb_make_pymatgen.py* scripts by @MoseyQAQ, which use IDPP of pymatgen to do NEB initial guess, avoiding IDPP problem from ASE including edge-crossing problem in NEB guess generation.
- Support DeepPotential and DPA-2 Potential usage scripts in `ase-dp` directory.
- New function: `neb2vib` method to use NEB chain information to do partial vibrational analysis.
- Thermochemistry analysis for ideal gas system.
- Examples Update

## Dependencies:

### Required dependencies
- [ASE](https://wiki.fysik.dtu.dk/ase/about.html), but you should install ASE by [ASE-ABACUS interface](https://gitlab.com/1041176461/ase-abacus) as a separate ASE package for ABACUS usage.
- [ABACUS](https://github.com/deepmodeling/abacus-develop), one can install ABACUS by ABACUS toolchain [ABACUS](https://github.com/deepmodeling/abacus-develop/tree/develop/toolchain), or refer to [ABACUS-docs](https://abacus.deepmodeling.com/en/latest/)

### Optional dependencies
- [Sella](https://github.com/zadorlab/sella) if one wants to use Sella method for Single-End TS search. which can be installed by `pip install sella`
- [GPAW](https://wiki.fysik.dtu.dk/gpaw/install.html) if one wants to run NEB images relaxation in parallel. The installation of GPAW need some efferts, and one can refer to [GPAW installation](https://wiki.fysik.dtu.dk/gpaw/install.html) for more details.
- [deepmd-kit](https://github.com/deepmodeling/deepmd-kit) or [DPA-2](https://zenodo.org/records/10428497) if one wants to use Deep-Potential or DPA-2 potential, one can refer to [deepmd-docs](https://docs.deepmodeling.com/projects/deepmd/en/master/)


Notice: GPAW and ABACUS should be dependent on same MPI and libraries environments. 
> For instance, if your ABACUS is installed by Intel-OneAPI toolchain, your GPAW should NOT be dependent on gcc-toolchain like OpenMPI and OpenBLAS.

ATST-Tools is Under actively development, please let me know if any problem occurs.

## Tutorials
- One can get ASE-ABACUS usage from this [Bohrium Notebook 1](https://bohrium.dp.tech/notebooks/6516485694)
- One can get NEB tutorial from this [Bohrium Notebook 2](https://nb.bohrium.dp.tech/detail/39369325971)
- One can get Single-End TS search tutorial from this [Bohrium Notebook 3](https://bohrium.dp.tech/notebooks/29581597682)
- D2S TS exploration tutorial is coming soon.

## Workflow

![ATST-NEB-workflow](./img/ATST-workflow.png)

## Workflow libraries and setting
All workflow library files and re-constructed ASE libraries will be put in `./source` directory. including:
```bash
source
├── abacus_autoneb.py
├── abacus_dimer.py
├── abacus_neb.py
├── my_autoneb.py
└── neb2vib.py
```
Before use running scripts, you should add these libraries into your PYTHONPATH:
```bash
export PYTHONPATH=/path/to/source:$PYTHONPATH
```

There are also other workflow in ATST-Tools
- AutoNEB TS exploration
- Double-to-Single (D2S) TS exploration

## Developing
- [ ] More fiexible options for NEB, Dimer and AutoNEB, like full properties in trajectory file, and fiexibly utilize SCF wavefunction/charge output files from previous calculation.
- [ ] Move workflow parts of Deep-Potential and DPA-2 potential to `source` directory
- [ ] Parallel NEB calculation for D2S method and DP usage
- [ ] [dflow](https://github.com/dptech-corp/dflow) version of ATST-Tools workflow
- [ ] Bond soft scanning and automatic reaction locating (proposed by [CLAM workflow](https://github.com/lalaheihaihei/catalyticLAM))
- [x] Test for Sella usage to get best performance
- [x] Checkout the problem in Dimer-ABACUS calculation
- [x] Inplement `neb2vib` method in  `neb2dimer` workflow for DPA-2 (and ABACUS)
- [x] Other TS method usage, like [Sella](https://github.com/zadorlab/sella)


## NEB workflow

### Method
- For serial NEB calculation, DyNEB, namely dynamic NEB method `ase.mep.neb.DyNEB` is for default used.
- For parallel NEB calculation, `ase.mep.neb.NEB` traditional method is for default used.
- The Improved Tangent NEB method `IT-NEB` and Climbing Image NEB method `CI-NEB` in ASE are also default used in this workflow, which is highly recommended by Sobervea. In `AutoNEB`, `eb` method is used for default, but Improved Tangent method is also recommended.
- Users can change lots of parameter for different NEB setting. one can refer to [ASE NEB calculator](https://wiki.fysik.dtu.dk/ase/ase/neb.html#module-ase.neb) for more details: 
- The workflow also support use `AutoNEB` method in ASE。You can view AutoNEB method in paper below. Also. One can refer to [AutoNEB](https://wiki.fysik.dtu.dk/ase/ase/neb.html#autoneb) to view it. 
> E. L. Kolsbjerg, M. N. Groves, and B. Hammer, J. Chem. Phys, 145, 094107, 2016. (doi: 10.1063/1.4961868)

The AutoNEB method in ASE lies in `ase.mep.autoneb.AutoNEB` object, which will do NEB calculation in following steps:
1. Define a set of images and name them sequentially. Must at least have a relaxed starting and ending image. User can supply intermediate guesses which do not need to have previously determined energies (probably from another
NEB calculation with a lower level of theory)
1. AutoNEB will first evaluate the user provided intermediate images
2. AutoNEB will then add additional images dynamically until n_max is reached
3. A climbing image will attempt to locate the saddle point
4. All the images between the highest point and the starting point are further relaxed to smooth the path
5. All the images between the highest point and the ending point are further relaxed to smooth the path

Step 4 and 5-6 are optional steps. Note that one can specify different `fmax` for CI-NEB in step 4 compared with other NEB calculation, which can be set as `fmax=[fmax1, fmax2]` in `AutoNEB` object.

> Notice: in surface calculation and hexangonal system, the vaccum and c-axis should be set along y-direction but not z-direction, which is much more efficient for ABACUS calculation.


### Usage
#### Basic NEB
The NEB workflow is based on 3 main python scripts and 1 workflow submit script. Namely:

- `neb_make.py` will make initial guess for NEB calculation, which is based on ABACUS (and other calculator) output files of initial and final state. This script will generate `init_neb_chain.traj` for neb calculation. Also, You can do continuation calculation by using this script. You can get more usage by `python neb_make.py`. 
- `neb_run.py` is the key running script of NEB, which will run NEB calculation based on `init_neb_chain.traj` generated by `neb_make.py`. This script will generate `neb.traj` for neb calculation. Users should edit this file to set parameters for NEB calculation. sereal running can be performed by `python neb_run.py`, while parallel running can be performed by `mpirun gpaw python neb_run.py`.
When running, the NEB trajectory will be output to `neb.traj`, and NEB images calculation will be doing in `NEB-rank{i}` directory for each rank which do calculation of each image. 
- `neb_post.py` will post-process the NEB calculation result, which will based on `neb.traj` from neb calculation. This script will generate nebplots.pdf to view neb calculation result, and also print out the energy barrier and reaction energy. You can get more usage by `python neb_post.py`. Meanwhile, users can also view result by `ase -T gui neb.traj` or `ase -T gui neb.traj@-{n_images}:` by using ASE-GUI
- `neb_submit.sh` will do all NEB process in one workflow scripts and running NEB calculation in parallel. Users should edit this file to set parameters for NEB calculation. Also this submit script can be used as a template for job submission in HPC. the Default setting is for `slurm` job submission system.

#### AutoNEB method 
In ATST-Tools, the AutoNEB method can be easily used by the following scripts
- `autoneb_run.py` is the key running script for `AutoNEB` method, which is like `neb_run.py` but the NEB workflow in `AutoNEB` is enhanced and the I/O logic have some difference. Users can use it with `mpirun gpaw python autoneb_run.py` by existing `init_neb_chain.traj` which can only contain initial and final state or contain some initial-guess.
- `autoneb_submit.sh` will do all AutoNEB process in one workflow and running AutoNEB calculation in parallel. Users should edit this file to set parameters for AutoNEB calculation. Also this submit script can be used as a template for job submission in HPC. the Default setting is for `slurm` job submission system.
- `neb_make.py` and `neb_post.py` can be used for `AutoNEB` method, but the workflow have slight difference. 

#### Running
Users can run NEB each step respectively: 
1. `python neb_make.py [INIT/result] [FINAL/result] [n_max]` to create initial guess of neb chain
   1. Also You can use `python neb_make.py -i [input_traj_file] [n_max]` to create initial guess from existing traj file, which can be used for continuation calculation.
2. `python neb_run.py` or `mpirun -np [nprocs] gpaw python neb_run.py` to run NEB calculation
3. `python neb_post.py neb.traj [n_max]` to post-process NEB calculation result

Users can run AutoNEB each step respectively:
1. `python neb_make.py -i [INIT/result] [FINAL/result] -n [nprocs]` to create initial guess of neb chain
2. `mpirun -np [nprocs] gpaw python autoneb_run.py` to run AutoNEB calculation
3. `python neb_post.py --autoneb run_autoneb???.traj` to post-process NEB calculation result

Also, user can run each step in one script `neb_submit.sh` by `bash neb_submit.sh` or `sbatch neb_submit.sh`. AutoNEB scripts usage is like that. 

> Notice: Before you start neb calculation process, make sure that you have check the nodes and cpus setting and other setting like n_max, constraints and initial magnetic moments in `*neb_submit.sh` and `*neb_run.py` to make sure that you can reach the highest performance and reach the simulation result you want !!!   

#### Visualize
You can simply use ASE-GUI to have a view of NEB or AutoNEB trajectory.

For NEB, you can view all running trajectory by 
```bash
ase -T gui neb.traj 
```
You can also view the last 10 images by
```bash
ase -T gui neb.traj@-10:
```
For AutoNEB, the most recent NEB path can always be monitored by:
```bash
ase -T gui -n -1 run_autoneb???.traj
```

#### Continuation calculation for NEB
If NEB or AutoNEB is break down somehow, you can do continuation calculation based on saved trajectory files and ATST-Tools scripts.

For NEB, you can simply:
```bash
python neb_make.py -i neb.traj -n [n_max] [fix and mag information]
```
to generate `init_neb_chain.traj` for continuation calculation. You can also `python neb_post.py neb.traj` to generate the latest neb band `neb_latest.traj` and do continuation calculation by `python neb_make.py -i neb_latest.traj [n_max]`. note that `n_max = n_image - 2`

For AutoNEB, you need to get `neb_latest.traj` in a more compicated way, especially for the first NEB step in AutoNEB running:
```bash
python traj_collect.py ./AutoNEB_iter/run_autoneb???iter[index].traj
```
to generate `collection.traj` from certain index (like 006) stage of AutoNEB calculation. Another way to do the same thing is:
```bash
python traj_collect.py ./run_autoneb???.traj
```
or
```bash
python traj_collect.py ./AutoNEB_iter/run_autoneb???iter00[i].traj
```
or
```bash
python traj_collect.py ./AutoNEBrun_rank?/STRU
```
When `collection.traj` is gotten, one can do
```bash
python neb_make.py -i collection.traj [n_max] [fix and mag information]
```
to generate `init_neb_chain.traj` for continuation calculation.

If one want to continue calculation with the interrupted autoneb, one can:
```bash
python traj_collect.py --no-calc ./run_autoneb???.traj 
```
and `--no-calc` noted can be anywhere.

> Note: Linux shell will automatically detect and sort number of index, so you will not be worried about using format like `run_autoneb???iter005.traj`, the consequence will be right, for example:
```bash
 test> ll run_autone*.traj
-rw-r--r-- 1 james james 6.0K Nov 24 20:35 run_autoneb000.traj
-rw-r--r-- 1 james james 6.4K Nov 24 20:35 run_autoneb001.traj
-rw-r--r-- 1 james james 6.4K Nov 24 20:35 run_autoneb002.traj
-rw-r--r-- 1 james james 531K Nov 24 20:35 run_autoneb003.traj
-rw-r--r-- 1 james james 531K Nov 24 20:35 run_autoneb004.traj
-rw-r--r-- 1 james james 531K Nov 24 20:35 run_autoneb005.traj
-rw-r--r-- 1 james james 531K Nov 24 20:35 run_autoneb006.traj
-rw-r--r-- 1 james james 6.4K Nov 24 20:35 run_autoneb007.traj
-rw-r--r-- 1 james james 6.4K Nov 24 20:35 run_autoneb008.traj
-rw-r--r-- 1 james james 6.5K Nov 24 20:35 run_autoneb009.traj
-rw-r--r-- 1 james james 6.5K Nov 24 20:35 run_autoneb010.traj
-rw-r--r-- 1 james james 6.5K Nov 24 20:35 run_autoneb011.traj
-rw-r--r-- 1 james james 6.5K Nov 24 20:35 run_autoneb012.traj
-rw-r--r-- 1 james james 531K Nov 24 20:37 run_autoneb025.traj
```


#### Other scripts
Because ATST is originally based on ASE, the trajectory file can be directly read, view and analysis by `ase gui` and other ASE tools. Abide by `neb_make.py` and `neb_post.py`, We also offer some scripts to help you:
- `neb_dist.py`: This script will give distance between initial and final state, which is good for you to check whether the atoms in two image is correspondent, and is also a reference for setting number of n_max
- `traj_transform.py`: This script can transfer traj files into other format like `extxyz`, `abacus`(STRU), `cif` and so on (coming soon). Also if user specify `--neb` option, this script will automatically detect and cut the NEB trajectory when doing format transform. This script will be helpful for analysis and visualization of NEB trajectory.
- `traj_collect.py`: This script can collect structure files into a trajectory file, which is specifically used for NEB continuation calculation.

## Single-End TS search

Contrary to NEB, the single-end TS search is based on the exploration of saddle point by using the gradient and Hessian (or only Hessian eigenmode) information of points in PES, which have good efficiency if one have an approximate TS information. ATST-Tools support Dimer method and Sella method.

### Sella workflow
The Sella workflow is based on 1 main python scripts and 1 submit script, namely:
- `sella_run.py`  is the key running script of Dimer calculation, which will run Sella calculation based on supplying `STRU` files for initial state of Sella calculation. This script will generate `run_sella.traj` for Sella calculation trajectory. Users should edit this file to set parameters for Sella calculation, and run Sella calculation by `python sella_run.py`. When running, any Sella images calculation will be doing in `ABACUS` directory.
- `sella_submit.sh` will do Sella workflow in one scripts. The Default setting is for `slurm` job submission system.

Also, Sella package can be used for IRC calculation, one can refer to `sella_IRC.py` for more details.

For more detail on Sella principle and usage, one can refer to [Sella](https://github.com/zadorlab/sella) and [Sella-wiki](https://github.com/zadorlab/sella/wiki)


### Dimer workflow

The Dimer workflow is based on 2 main python scripts and 1 workflow submit script, namely:
- `neb2dimer.py` can be used by `python neb2dimer [neb.traj] ([n_max])`, which will transform NEB trajetory `neb.traj` or NEB result trajectory `neb_result.traj` to Dimer input files,  including:
- - `dimer_init.traj` for initial state of Dimer calculation, which is the highest energy image, namely, TS state. 
- - `STRU` files, representing the initial state of Dimer calculation, stored as `STRU` files for ABACUS calculation.
- - `displacement_vector.npy` for displacement vector of Dimer calculation, which will be generated from position minus of the nearest image before and after TS point, and be normalized to 0.01 Angstrom. 
- `dimer_run.py` is the key running script of Dimer calculation, which will run Dimer calculation based on `dimer_init.traj` and `displacement_vector.npy` generated by `neb2dimer.py` or based on other setting. This script will generate `run_dimer.traj` for Dimer calculation trajectory. Users should edit this file to set parameters for Dimer calculation, and run Dimer calculation by `python dimer_run.py`. When running, any Dimer images calculation will be doing in `ABACUS` directory.
- `dimer_submit.sh` will do Dimer workflow in one scripts. The Default setting is for `slurm` job submission system.


## Double-to-single (D2S) TS exploration

ATST-Tools also offer a double-to-single (D2S) TS exploration method, which is named as `neb2dimer_abacus.py` and `neb2sella_abacus.py` in `dimer` and `sella` directories respectively, which run a rough NEB first and use the maximum information for initial guess of running single-ended method like dimer or Sella, obtaining a high-efficiency TS exploration. 

In D2S workflow, Dynamic NEB acceleration is used for NEB calculation for serial usage for faster rough NEB calculation.

This workflow is only for serial NEB calculation, but is efficient enough for TS exploration. The parallel NEB acceleration is in considering.

## Vibration Analysis 
The vibration analysis is based on `ase.vibrations.Vibrations` object, which can be used by `python vib_analysis.py` to do vibration analysis by finite displacement method for initial, final and transition state. The result will be printed out  and saved in `running_vib.out` file. All force matrix for displaced and normal mode will also be saved and printed.

Also, thermodynamic analysis will be performed based on `ase.thermochemistry.HarmonicThermo` object based on vibration analysis result and specified temperature.

## Relaxation
Relaxation method offer by ASE can be used by scripts from `relax` directory, which use ABACUS as SCF calculator. 
> Notes: QuasiNewton method in ASE is BFGSLineSearch, which is default usage in ATST-Tools and can have robust structural relaxation ability.

## ase-dp
There are also scripts for Deep-Potential and DPA-2 potential usage in `ase-dp` directory for TS exploration and structural relaxation, some newest examples can be used by `neb2dimer_dp.py`, `neb2sella_dp.py` and `relax_dp.py` for Deep-Potential and DPA-2 potential usage. 

Parallel NEB version for ase-dp is also in developing.

## Examples
- Li-diffu-Si: Li diffusion in Si, very easy example for serial and parallel NEB calculation about diffusion system. Note that ATS-Tools will tune the parameters towards TS exploration, for those who want to do diffusion calculation, one should check the effectiveness of the parameters by yourself.
- H2-Au111: H2 dissociation on Au(111) surface. which will have NEB, serial DyNEB, AutoNEB, Dimer, Sella and D2S example. The barrier is around 1.1 eV consistent with existing paper and calculation result. IRC results shows the reaction path is correct.
- CO-Pt111 : CO dissociation on Pt(111) surface. which have high barrier as 1.5 eV and including diffusion part. AutoNEB will always fail due to the low starting image. By performing Dimer / Sella calculation, or use the D2S method, the TS can be explored in an efficient and accurate way. By using Sella package, one can also get the IRC of C-O dissociaition reaction process.
- Cy-Pt_graphene: Cyclohexane dehydrogenation on Pt-doped graphene surface. The barrier is around 1.3 eV. Noted that the `IT-NEB` result is wrong, but which is consistent to the result in VTST-Tools when using 4 image to do IT-NEB calculation. Dimer calculation also get wrong result in this case, while Sella perform good result.

More examples is welcomed from users. 

## Notices
### Property Loss in Trajectory 
Some property should be get via specific way from trajectory files, and some will be lost in trajetory files, 
- Stress property will not be stored in trajetory file
- In NEB calculation, the Force property for fixed atoms and Stress property will NOT be stored in trajectory file, one should get it by `get_force(apply_constraint=False)`.
- in Dimer calculation, the Energy, Forces and Stress property will be stored in trajetory file after specified which properties need to be stored. (Sella calculation should be likely) (The most easiest lost information is the stress information)
- in AutoNEB calculation, all property in processing trajectory will be stored in AutoNEB_iter directory, but in the result `run_autoneb???.traj`, the forces and stress information will be lost.


