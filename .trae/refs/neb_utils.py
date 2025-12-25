#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
极速 IDPP 路径生成脚本 (无几何对齐版)。
仅执行原子索引对齐和 IDPP 插值，不进行任何旋转或平移操作。

使用方法:
    python idpp_neb_clean.py IS.vasp FS.vasp -n 8 -o initial_path.traj
"""

import os
import argparse
import numpy as np
import warnings
from typing import List

# ASE Imports
from ase import Atoms
from ase.io import read, write
# 注意：已移除 ase.build.rotate 引用

# Scipy Imports
from scipy.optimize import linear_sum_assignment, minimize

# ==========================================
# 核心类与函数定义
# ==========================================

def align_atom_indices(atoms_ref: Atoms, atoms_target: Atoms) -> Atoms:
    """
    重新排列 atoms_target 的原子索引，使其尽可能与 atoms_ref 对应。
    注意：此函数只交换原子编号，绝对不移动原子的空间坐标。
    """
    if len(atoms_ref) != len(atoms_target):
        raise ValueError(f"原子数量不一致 (Ref: {len(atoms_ref)}, Target: {len(atoms_target)})，无法对齐！")
    
    new_indices = np.zeros(len(atoms_ref), dtype=int)
    
    # 预计算
    cell = atoms_ref.get_cell()
    pbc = atoms_ref.get_pbc()
    # 只有当开启 PBC 且 cell 不为零时才计算逆矩阵
    if np.any(pbc) and np.linalg.det(cell) > 1e-8:
        inv_cell = np.linalg.inv(cell)
        use_mic = True
    else:
        use_mic = False
    
    chemical_symbols = np.array(atoms_ref.get_chemical_symbols())
    unique_elements = sorted(list(set(chemical_symbols)))
    
    ref_pos = atoms_ref.get_positions()
    target_pos = atoms_target.get_positions()
    
    total_dist_sq = 0.0
    
    for element in unique_elements:
        # 1. 按元素分组
        mask = (chemical_symbols == element)
        indices_ref = np.where(mask)[0]
        
        target_symbols = np.array(atoms_target.get_chemical_symbols())
        indices_target = np.where(target_symbols == element)[0]
        
        if len(indices_ref) != len(indices_target):
            raise ValueError(f"元素 {element} 的数量在两个结构中不一致！")
            
        n_elem = len(indices_ref)
        
        # 2. 构建成本矩阵
        pos_sub_ref = ref_pos[indices_ref]       
        pos_sub_target = target_pos[indices_target] 
        
        # 向量化差值: (n, 1, 3) - (1, n, 3) -> (n, n, 3)
        diff = pos_sub_ref[:, np.newaxis, :] - pos_sub_target[np.newaxis, :, :]
        
        # 3. 最小镜像约定 (MIC) - 仅用于计算距离矩阵，不改变坐标
        if use_mic:
            scaled_diff = np.dot(diff, inv_cell)
            scaled_diff -= np.round(scaled_diff)
            diff = np.dot(scaled_diff, cell)
            
        dist_matrix_sq = np.sum(diff**2, axis=2)
        
        # 4. 匈牙利算法
        row_ind, col_ind = linear_sum_assignment(dist_matrix_sq)
        
        # 5. 映射索引
        for k in range(n_elem):
            global_idx_ref = indices_ref[row_ind[k]]
            global_idx_target = indices_target[col_ind[k]]
            new_indices[global_idx_ref] = global_idx_target
            total_dist_sq += dist_matrix_sq[row_ind[k], col_ind[k]]

    print(f"  [Alignment] 索引对齐完成。当前几何位置下的 MSD: {total_dist_sq:.4f} Å²")
    
    # 按照新索引重排原子，继承 ref 的晶胞信息
    sorted_atoms = atoms_target[new_indices]
    sorted_atoms.set_cell(atoms_ref.get_cell())
    sorted_atoms.set_pbc(atoms_ref.get_pbc())
    
    return sorted_atoms


def robust_interpolate(start_atoms: Atoms, end_atoms: Atoms, nimages: int) -> List[Atoms]:
    """对周期性边界条件健壮的线性插值函数。"""
    scaled_start = start_atoms.get_scaled_positions()
    scaled_end = end_atoms.get_scaled_positions()
    delta_scaled = scaled_end - scaled_start
    delta_scaled_mic = delta_scaled - np.round(delta_scaled)
    
    path = [start_atoms.copy()]
    total_steps = nimages + 1
    for i in range(1, total_steps):
        alpha = i / total_steps
        current_scaled_pos = scaled_start + alpha * delta_scaled_mic
        image = start_atoms.copy()
        image.set_scaled_positions(current_scaled_pos)
        path.append(image)
    path.append(end_atoms.copy())
    return path


class Fast_IDPPSolver:
    """
    基于 Scipy L-BFGS-B 的极速 IDPP 求解器。
    """
    def __init__(self, images: list[Atoms], mic: bool = True):
        self.start_atoms = images[0]
        self.end_atoms = images[-1]
        self.nimages = len(images) - 2
        self.natoms = len(self.start_atoms)
        self.cell = self.start_atoms.get_cell()
        
        if mic and np.linalg.det(self.cell) > 1e-8:
            self.inv_cell = np.linalg.inv(self.cell)
            self.mic = True
        else:
            self.inv_cell = np.eye(3)
            self.mic = False

        # 1. 预计算目标距离矩阵
        d_start = self.start_atoms.get_all_distances(mic=self.mic)
        d_end = self.end_atoms.get_all_distances(mic=self.mic)
        
        factors = np.linspace(0, 1, self.nimages + 2)[1:-1]
        self.target_dists = d_start[None, :, :] + factors[:, None, None] * (d_end - d_start)[None, :, :]

        # 2. 预计算权重
        avg_dists = (d_start[None, :, :] + d_end[None, :, :]) / 2.0 
        self.weights = 1.0 / (avg_dists**4 + np.eye(self.natoms)[None, :, :] * 1e-12)

        self.initial_positions = np.array([img.get_positions() for img in images[1:-1]])

    def _objective_function(self, flat_coords):
        coords = flat_coords.reshape((self.nimages, self.natoms, 3))
        
        if self.mic:
            scaled_coords = np.dot(coords, self.inv_cell)
            diff_scaled = scaled_coords[:, :, None, :] - scaled_coords[:, None, :, :]
            diff_scaled -= np.round(diff_scaled)
            vectors = np.dot(diff_scaled, self.cell)
        else:
            vectors = coords[:, :, None, :] - coords[:, None, :, :]

        current_dists = np.linalg.norm(vectors, axis=3)
        delta_dists = current_dists - self.target_dists
        energy = 0.5 * np.sum(self.weights * delta_dists**2)

        with np.errstate(divide='ignore', invalid='ignore'):
            prefactor = (self.weights * delta_dists) / (current_dists + 1e-12)
        
        gradients = 2.0 * np.einsum('nij,nijk->nik', prefactor, vectors)
        return energy, gradients.flatten()

    def run(self, maxiter=500, tol=1e-4):
        print(f"  [IDPP] 开始 L-BFGS-B 优化 ({self.nimages} 个中间构型)...")
        x0 = self.initial_positions.flatten()
        res = minimize(
            self._objective_function, x0, method='L-BFGS-B', jac=True, 
            options={'maxiter': maxiter, 'gtol': tol, 'disp': False}
        )
        
        final_grads = res.jac.reshape((self.nimages, self.natoms, 3))
        fmax = np.max(np.linalg.norm(final_grads, axis=2))
        
        print("-" * 60)
        print("                 IDPP CONVERGENCE REPORT            ")
        print("-" * 60)
        print(f"  Status       : {'✅ Converged' if res.success else '❌ Failed'}")
        print(f"  Message      : {res.message}")
        print(f"  Iterations   : {res.nit}")
        print(f"  Final S_IDPP : {res.fun:.6f}")
        print(f"  Max Force    : {fmax:.6f} (Target: < {tol})")
        print("-" * 60)

        if not res.success:
            warnings.warn(f"IDPP 未完全收敛: {res.message}")

        optimized_coords = res.x.reshape((self.nimages, self.natoms, 3))
        final_images = [self.start_atoms.copy()]
        for i in range(self.nimages):
            img = self.start_atoms.copy()
            img.set_positions(optimized_coords[i])
            final_images.append(img)
        final_images.append(self.end_atoms.copy())
        
        return final_images

    @classmethod
    def from_endpoints(cls, start: Atoms, end: Atoms, nimages: int):
        initial_images = robust_interpolate(start, end, nimages)
        return cls(initial_images)


# ==========================================
# 主程序逻辑
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="生成基于 IDPP 的 NEB 初始路径 (无几何对齐，仅插值)。")
    
    # 输入参数
    parser.add_argument("is_file", help="初态结构文件 (IS)")
    parser.add_argument("fs_file", help="末态结构文件 (FS)")
    
    # 选项参数
    parser.add_argument("-n", "--nimages", type=int, default=5, help="中间插值点的数量 (默认: 5)")
    parser.add_argument("-o", "--output", default="idpp_path.traj", help="输出路径文件名 (默认: idpp_path.traj)")
    parser.add_argument("--format", default=None, help="输出文件格式 (例如: extxyz, cif, POSCAR)")
    parser.add_argument("--no-align", action="store_true", help="跳过原子索引自动对齐 (如果索引已完全一致可跳过)")
    parser.add_argument("--tol", type=float, default=0.05, help="IDPP 收敛力判据 (eV/A, 默认: 0.05)")
    
    args = parser.parse_args()

    # 1. 读取文件
    print(f"正在读取文件:\n  IS: {args.is_file}\n  FS: {args.fs_file}")
    try:
        IS = read(args.is_file)
        FS = read(args.fs_file)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return

    # 2. 原子索引对齐 (仅交换编号，不移动坐标)
    FS_processed = FS.copy()
    if not args.no_align:
        print("正在检查原子索引一致性 (Hungarian Algorithm)...")
        try:
            # 这一步仅重新排列 FS_processed 的原子顺序列表
            FS_processed = align_atom_indices(IS, FS)
        except Exception as e:
            print(f"❌ 索引对齐失败: {e}")
            return
    else:
        print("⚠️ 跳过原子索引对齐，假设输入索引完全一致。")

    # 3. 运行 IDPP
    print(f"正在生成包含 {args.nimages} 个中间像的 IDPP 路径...")
    # 注意：这里直接使用输入的 IS 和 (索引对齐后的) FS
    # 不会进行 minimize_rotation_and_translation
    solver = Fast_IDPPSolver.from_endpoints(IS, FS_processed, args.nimages)
    path = solver.run(tol=args.tol)

    # 4. 保存输出
    print(f"正在保存路径到: {args.output}")
    if args.output.endswith(".traj"):
        write(args.output, path)
    else:
        write(args.output, path, format=args.format)
    
    print("✅ 任务完成！")

if __name__ == "__main__":
    main()