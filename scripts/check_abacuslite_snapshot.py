#!/usr/bin/env python3
"""Compare ATST's vendored abacuslite snapshot with a pinned upstream tree."""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import re
import tokenize
from pathlib import Path
from typing import Iterable


IGNORED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
VENDORED_ONLY_FILES = {
    Path("__init__.py"),
    Path("ABACUSLITE_SNAPSHOT.md"),
    Path("PATCHES.md"),
}


def _is_vendored_only(relative_path: Path) -> bool:
    """atst 自有文件：顶层基线/补丁文档，以及 curated 多帧金样目录（upstream 无此夹具）。"""
    if relative_path in VENDORED_ONLY_FILES:
        return True
    parts = relative_path.parts
    return (
        parts[:3] == ("abacuslite", "io", "testfiles")
        and parts[3].startswith("multiframe_")
    )


def _legacy_band_parser_tolerant_block(indent: str) -> str:
    return (
        f"{indent}while j < len(raw) and len(rows) < nbnd:\n"
        f"{indent}    parts = raw[j].strip().split()\n"
        f"{indent}    if len(parts) >= 3 and parts[0].isdigit():\n"
        f"{indent}        try:\n"
        f"{indent}            rows.append([float(parts[0]), float(parts[1]), float(parts[2])])\n"
        f"{indent}        except ValueError:\n"
        f"{indent}            pass\n"
        f"{indent}    j += 1"
    )


def _is_ignored(relative_path: Path) -> bool:
    if any(part in IGNORED_DIR_NAMES or part.endswith(".egg-info") for part in relative_path.parts):
        return True
    return relative_path.suffix in IGNORED_SUFFIXES


def _iter_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and not _is_ignored(path.relative_to(root))
    }


def _node_line_range(node: ast.AST) -> range:
    first_line = getattr(node, "lineno")
    for decorator in getattr(node, "decorator_list", []):
        first_line = min(first_line, decorator.lineno)
    end_line = getattr(node, "end_lineno", first_line)
    return range(first_line, end_line + 1)


def _is_test_function(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")


def _is_test_only_class(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef) or not node.name.startswith("Test"):
        return False

    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return bool(body) and all(_is_test_function(child) for child in body)


def _remove_embedded_test_methods(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    lines = source.splitlines()
    remove_ranges: list[range] = []
    remove_lines: set[int] = set()
    for node in tree.body:
        if _is_test_function(node):
            remove_ranges.append(_node_line_range(node))
        elif _is_test_only_class(node):
            remove_ranges.append(_node_line_range(node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            remove_ranges.extend(
                _node_line_range(child) for child in node.body if _is_test_function(child)
            )

    for line_range in remove_ranges:
        remove_lines.update(line_range)
        first_line = line_range.start
        last_line = line_range.stop - 1
        if first_line > 1 and not lines[first_line - 2].strip():
            remove_lines.add(first_line - 1)
        if last_line < len(lines) and not lines[last_line].strip():
            remove_lines.add(last_line + 1)

    if not remove_lines:
        return source

    filtered = [line for lineno, line in enumerate(lines, start=1) if lineno not in remove_lines]
    text = "\n".join(filtered)
    return f"{text}\n" if source.endswith("\n") else text


def _remove_module_level_functions(source: str, names: set[str]) -> str:
    """移除指定模块级函数（AST 行区间 + 相邻空行清理），未找到则原样返回。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    remove_ranges = [
        _node_line_range(node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    if not remove_ranges:
        return source

    lines = source.splitlines()
    remove_lines: set[int] = set()
    for line_range in remove_ranges:
        remove_lines.update(line_range)
        first_line = line_range.start
        last_line = line_range.stop - 1
        if first_line > 1 and not lines[first_line - 2].strip():
            remove_lines.add(first_line - 1)
        if last_line < len(lines) and not lines[last_line].strip():
            remove_lines.add(last_line + 1)

    filtered = [line for lineno, line in enumerate(lines, start=1) if lineno not in remove_lines]
    text = "\n".join(filtered)
    return f"{text}\n" if source.endswith("\n") else text


def _normalize_packaging_imports(source: str) -> str:
    replacements = {
        "from .io.generalio import": "from abacuslite.io.generalio import",
        "from .io.legacyio import": "from abacuslite.io.legacyio import",
        "from .io.latestio import": "from abacuslite.io.latestio import",
        "from .legacyio import": "from abacuslite.io.legacyio import",
    }
    for before, after in replacements.items():
        source = source.replace(before, after)
    return source


def _normalize_python_comment_churn(source: str) -> str:
    try:
        remove_lines: set[int] = set()
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and not token.line[: token.start[1]].strip():
                remove_lines.add(token.start[0])
            elif token.type == tokenize.NL and not token.line.strip():
                remove_lines.add(token.start[0])
    except tokenize.TokenError:
        return source
    if not remove_lines:
        return source

    lines = source.splitlines()
    filtered = [line for line_number, line in enumerate(lines, start=1) if line_number not in remove_lines]
    text = "\n".join(filtered)
    return f"{text}\n" if source.endswith("\n") else text


def _normalize_legacy_band_parser_adaptation(source: str) -> str:
    strict_pattern = re.compile(
        r"(?P<indent>[ \t]*)while j < len\(raw\) and len\(rows\) < nbnd:\n"
        r"(?P=indent)    if re\.match\(ekb_leading_pat, raw\[j\]\):\n"
        r"(?P=indent)        break\n"
        r"(?P=indent)    parts = raw\[j\]\.strip\(\)\.split\(\)\n"
        r"(?P=indent)    if len\(parts\) >= 3 and parts\[0\]\.isdigit\(\):\n"
        r"(?P=indent)        try:\n"
        r"(?P=indent)            band_index = int\(parts\[0\]\)\n"
        r"(?P=indent)            if band_index == len\(rows\) \+ 1:\n"
        r"(?P=indent)                rows\.append\(\[float\(parts\[0\]\), float\(parts\[1\]\), float\(parts\[2\]\)\]\)\n"
        r"(?P=indent)        except ValueError:\n"
        r"(?P=indent)            pass\n"
        r"(?P=indent)    j \+= 1"
    )
    return strict_pattern.sub(
        lambda match: _legacy_band_parser_tolerant_block(match.group("indent")),
        source,
    )


def _normalize_efermi_tolerance(relative_path: Path, source: str) -> str:
    """efermi 容错语义补丁（spec PATCHES.md 登记）：ener['E_Fermi'] -> ener.get('E_Fermi'）。
    仅作用于 SinglePointDFTCalculator 构造行的 efermi 关键字，不改变其他语义。"""
    if relative_path not in {
        Path("abacuslite/io/legacyio.py"),
        Path("abacuslite/io/latestio.py"),
    }:
        return source
    return source.replace("efermi=ener['E_Fermi']", "efermi=ener.get('E_Fermi')")


_FRAME_SELECTION_BLOCK = re.compile(
    r"(?P<indent>[ \t]*)outdir = directory / f'OUT\.\{self\.suffix\}'\n"
    r"(?P=indent)log = outdir / f'running_\{self\.calculation\}\.log'\n"
    r"(?P=indent)#[^\n]*\n"
    r"(?P=indent)frames = read_abacus_out\(log, sort_atoms_with=self\.atomorder\)\n"
    r"(?P=indent)if not frames:\n"
    r"(?P=indent)    raise RuntimeError\(f\"no ABACUS running-log frames in \{log\}\"\)\n"
    r"(?P=indent)if self\.calculation != 'scf':\n"
    r"(?P=indent)    atoms: Optional\[Atoms\] = frames\[-1\][^\n]*\n"
    r"(?P=indent)else:\n"
    r"(?:(?P=indent)    #[^\n]*\n)*"
    r"(?P=indent)    atomorder = self\.atomorder or list\(range\(len\(frames\[0\]\)\)\)\n"
    r"(?P=indent)    atoms = _select_scf_frame_for_structure\(frames, log, directory, atomorder\)\n"
    r"(?P=indent)assert atoms is not None"
)


def _upstream_read_results_tail(indent: str) -> str:
    return (
        f"{indent}outdir = directory / f'OUT.{{self.suffix}}'\n"
        f"{indent}# only the last frame\n"
        f"{indent}atoms: Optional[Atoms] = read_abacus_out(\n"
        f"{indent}    outdir / f'running_{{self.calculation}}.log',\n"
        f"{indent}    sort_atoms_with=self.atomorder)[-1]\n"
        f"{indent}assert atoms is not None"
    )


def _normalize_frame_selection(source: str) -> str:
    """core.py 帧选择语义补丁（spec PATCHES.md 登记）：移除模块级辅助函数，
    并把 read_results 的 scf/non-scf 分支还原为上游 [-1] 单行形式。
    未匹配（补丁已演化）则原样返回，保持未登记 drift 报警。"""
    source = _remove_module_level_functions(
        source,
        {"_stru_positions_in_ase_order", "_frame_coordinate_is_direct", "_select_scf_frame_for_structure"},
    )
    return _FRAME_SELECTION_BLOCK.sub(
        lambda match: _upstream_read_results_tail(match.group("indent")),
        source,
    )


def _normalize_documented_atst_adaptations(relative_path: Path, source: str) -> str:
    source = _normalize_efermi_tolerance(relative_path, source)
    if relative_path == Path("abacuslite/io/legacyio.py"):
        return _normalize_legacy_band_parser_adaptation(source)
    if relative_path == Path("abacuslite/core.py"):
        return _normalize_frame_selection(source)
    return source


def _normalized_text(root: Path, relative_path: Path) -> str:
    source = (root / relative_path).read_text(encoding="utf-8")
    if relative_path.suffix == ".py" and relative_path.parts and relative_path.parts[0] == "abacuslite":
        source = _remove_embedded_test_methods(source)
        source = _normalize_packaging_imports(source)
        source = _normalize_documented_atst_adaptations(relative_path, source)
        source = _normalize_python_comment_churn(source)
    source = re.sub(r"[ \t]+$", "", source, flags=re.MULTILINE)
    return source


def _format_file_list(title: str, paths: Iterable[Path]) -> list[str]:
    listed = sorted(paths)
    if not listed:
        return []
    return [title, *[f"  - {path.as_posix()}" for path in listed]]


def compare_snapshots(upstream: Path, vendored: Path) -> int:
    """Return zero when vendored abacuslite matches the normalized upstream tree."""
    upstream = upstream.resolve()
    vendored = vendored.resolve()
    upstream_files = _iter_files(upstream)
    vendored_files = _iter_files(vendored)

    missing = upstream_files - vendored_files
    extra = {p for p in (vendored_files - upstream_files) if not _is_vendored_only(p)}
    output: list[str] = []
    output.extend(_format_file_list("Missing vendored files:", missing))
    output.extend(_format_file_list("Unexpected vendored-only files:", extra))

    for relative_path in sorted(upstream_files & vendored_files):
        upstream_text = _normalized_text(upstream, relative_path)
        vendored_text = _normalized_text(vendored, relative_path)
        if upstream_text == vendored_text:
            continue
        diff = difflib.unified_diff(
            upstream_text.splitlines(),
            vendored_text.splitlines(),
            fromfile=f"upstream/{relative_path.as_posix()}",
            tofile=f"vendored/{relative_path.as_posix()}",
            lineterm="",
        )
        output.append(f"Implementation drift detected in {relative_path.as_posix()}:")
        output.extend(diff)

    if output:
        print("\n".join(output))
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the snapshot comparison command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True, type=Path, help="Path to upstream interfaces/ASE_interface")
    parser.add_argument("--vendored", required=True, type=Path, help="Path to ATST vendored ASE_interface")
    args = parser.parse_args(argv)
    if not args.upstream.exists():
        raise SystemExit(f"Upstream path does not exist: {args.upstream}")
    if not args.vendored.exists():
        raise SystemExit(f"Vendored path does not exist: {args.vendored}")
    return compare_snapshots(args.upstream, args.vendored)


if __name__ == "__main__":
    raise SystemExit(main())
