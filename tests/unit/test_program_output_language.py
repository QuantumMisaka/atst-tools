"""Runtime program output must be English (no CJK literals in messages).

The scan below is a mechanical AST check over ``src/atst_tools``: a string
literal is flagged only when it is reachable from the arguments of a
runtime-visible output call. Docstrings, comments and other developer-facing
strings (module constants, comparison tables, ...) are intentionally allowed.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src/atst_tools"
# Vendored upstream snapshot (abacuslite); not maintained for output language.
VENDORED_DIRNAME = "external"

# CJK Unified Ideographs (+ Ext A, compatibility ideographs) and CJK
# punctuation such as 。、，. Narrow by design: fullwidth Latin forms and
# other scripts are not part of this contract.
_CJK_PATTERN = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# ``logging``/logger level methods whose message argument is runtime output.
_LOGGING_METHODS = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception"}
)

_SNIPPET_LIMIT = 80


def _is_output_call(func: ast.expr) -> bool:
    """Return whether a call target is a runtime-visible output sink."""
    if isinstance(func, ast.Name):
        return func.id == "print"
    if isinstance(func, ast.Attribute):
        # ``warnings.warn(...)`` and module/class-level ``warn(...)`` helpers.
        if func.attr == "warn":
            return True
        return func.attr in _LOGGING_METHODS
    return False


def _output_arguments(node: ast.Call | ast.Raise) -> list[ast.expr]:
    """Return the argument expressions that carry runtime-visible messages."""
    if isinstance(node, ast.Call):
        return [*node.args, *(keyword.value for keyword in node.keywords)]
    # ``raise <Exception>(...)``: the message argument of the raised call. All
    # positional/keyword arguments of the exception constructor are scanned, so
    # a message passed positionally is always covered.
    exception = node.exc
    if isinstance(exception, ast.Call):
        return [*exception.args, *(keyword.value for keyword in exception.keywords)]
    if isinstance(exception, ast.expr):
        return [exception]
    return []


def _string_constants(node: ast.expr) -> Iterator[ast.Constant]:
    """Yield string constants inside an expression, including f-string parts."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value:
            yield sub


def _format_offender(path: Path, constant: ast.Constant) -> str:
    """Format one finding as ``path:line: snippet``."""
    snippet = repr(constant.value)
    if len(snippet) > _SNIPPET_LIMIT:
        snippet = snippet[: _SNIPPET_LIMIT - 3] + "..."
    return f"{path}:{constant.lineno}: {snippet}"


def find_cjk_output_literals(path: str | Path) -> list[str]:
    """Return CJK runtime-visible literals of one module as ``path:line: snippet``.

    The module is parsed, never imported, so the scan stays fast and free of
    side effects.
    """
    module_path = Path(path)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_output_call(node.func):
            targets = _output_arguments(node)
        elif isinstance(node, ast.Raise):
            targets = _output_arguments(node)
        else:
            continue
        for target in targets:
            for constant in _string_constants(target):
                if _CJK_PATTERN.search(constant.value):
                    offenders.append(_format_offender(module_path, constant))
    return sorted(set(offenders))


def scan_source_tree(root: str | Path = SRC_ROOT) -> list[str]:
    """Return every offending literal below ``root`` (vendored tree skipped)."""
    root_path = Path(root)
    offenders: list[str] = []
    for module_path in sorted(root_path.rglob("*.py")):
        relative = module_path.relative_to(root_path)
        if relative.parts and relative.parts[0] == VENDORED_DIRNAME:
            continue
        offenders.extend(find_cjk_output_literals(module_path))
    return offenders


def test_runtime_output_strings_are_english():
    offenders = scan_source_tree()
    assert offenders == [], (
        "Runtime-visible CJK string literals found in src/atst_tools; translate "
        "them to English (docstrings and comments are not part of this check):\n"
        + "\n".join(offenders)
    )


def test_scan_detects_cjk_print_raise_and_logging(tmp_path):
    module = tmp_path / "cjk_runtime.py"
    module.write_text(
        "\n".join(
            [
                "import logging",
                "import warnings",
                "",
                "LOGGER = logging.getLogger(__name__)",
                "",
                "def run(workflow):",
                '    print("缺少 INPUT")',
                '    LOGGER.info(f"尚未支持的 workflow: {workflow}")',
                '    warnings.warn("不支持的 KPT 模式")',
                '    raise ValueError("不支持的 KPT 模式")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    offenders = find_cjk_output_literals(module)

    assert len(offenders) == 4, offenders
    assert any(item.startswith(f"{module}:7:") for item in offenders)
    assert any(item.startswith(f"{module}:8:") for item in offenders)
    assert any(item.startswith(f"{module}:9:") for item in offenders)
    assert any(item.startswith(f"{module}:10:") for item in offenders)


def test_scan_ignores_docstrings_and_comments(tmp_path):
    module = tmp_path / "cjk_dev_only.py"
    module.write_text(
        "\n".join(
            [
                '"""模块级 docstring：中文说明。"""',
                "",
                "# 中文注释：仅供开发者阅读",
                'DEVELOPER_TABLE = {"gamma": "伽马点"}',
                "",
                "def run(run_dir):",
                '    """缺少 INPUT 时抛错。"""',
                '    print(f"ABACUS run directory is missing INPUT: {run_dir}")',
                '    raise ValueError("Unsupported KPT mode")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert find_cjk_output_literals(module) == []


def test_scan_reports_clean_module_as_clean(tmp_path):
    module = tmp_path / "clean_runtime.py"
    module.write_text(
        "\n".join(
            [
                "import warnings",
                "",
                "def run(run_dir):",
                '    print(f"ABACUS run directory: {run_dir}")',
                '    warnings.warn("Endpoint directory lacks parseable output")',
                '    raise FileNotFoundError("ABACUS run directory does not exist")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert find_cjk_output_literals(module) == []
    assert scan_source_tree(tmp_path) == []
