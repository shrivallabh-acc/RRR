#!/usr/bin/env python
"""Comment coverage linter — verifies every module, class, and non-trivial function/method
has a docstring (per .claude/rules/comment-standards.md).

Static and stdlib-only (no extra deps). Run as part of the quality gate or standalone.

Exit codes:
  0 — all files pass
  1 — at least one violation found

Run:
  .venv/Scripts/python.exe scripts/check_comments.py src/rrr
  .venv/Scripts/python.exe scripts/check_comments.py src/rrr --verbose
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Functions/methods with a body shorter than this (in statements) are exempt
# from the docstring requirement — they are simple enough to self-document.
_BODY_STATEMENT_MINIMUM = 3

# Files we never flag — they are purely structural with no business logic.
_EXEMPT_FILENAMES = {"__init__.py", "__main__.py", "conftest.py", "py.typed"}

# Prefixes of names we never require docstrings for (Pydantic validators, overrides).
_EXEMPT_NAME_PREFIXES = ("model_", "__")


def _is_trivial_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when a function body is short enough to be self-documenting.

    We count only real statements — a docstring-only body (just an Expr(Constant))
    is NOT trivial; it's already documented. A single-statement return with no
    docstring is exempt.
    """
    stmts = node.body
    # Strip the leading docstring-node if it is already present.
    if stmts and isinstance(stmts[0], ast.Expr) and isinstance(stmts[0].value, ast.Constant):
        stmts = stmts[1:]
    return len(stmts) < _BODY_STATEMENT_MINIMUM


def _has_docstring(node: ast.AST) -> bool:
    """Return True when the first statement of a class/function body is a string literal."""
    body = getattr(node, "body", [])
    if not body:
        return False
    first = body[0]
    return isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)


def _exempt_name(name: str) -> bool:
    """Return True for names that are conventionally exempt from docstring requirements."""
    return any(name.startswith(prefix) for prefix in _EXEMPT_NAME_PREFIXES)


class _Violation:
    """A single missing-docstring finding."""

    def __init__(self, path: Path, line: int, kind: str, name: str) -> None:
        self.path = path
        self.line = line
        self.kind = kind
        self.name = name

    def __str__(self) -> str:
        return f"  MISSING {self.kind:10s} docstring  {self.path}:{self.line}  ({self.name})"


def _check_file(path: Path) -> list[_Violation]:
    """Parse one Python file and return all docstring violations.

    Checks module, class, and function/method nodes. Functions whose body is
    fewer than _BODY_STATEMENT_MINIMUM statements are exempt — they read like
    a one-liner and a docstring would be noise.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        # Unparseable file — report as a single violation so it doesn't silently pass.
        return [_Violation(path, exc.lineno or 0, "SYNTAX ", str(exc))]

    violations: list[_Violation] = []

    # Check the module-level docstring.
    if not _has_docstring(tree):
        violations.append(_Violation(path, 1, "MODULE ", path.name))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if not _has_docstring(node):
                violations.append(_Violation(path, node.lineno, "CLASS  ", node.name))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _exempt_name(node.name):
                continue
            if _is_trivial_body(node):
                continue
            if not _has_docstring(node):
                violations.append(_Violation(path, node.lineno, "FUNC   ", node.name))

    return violations


def _collect_python_files(target: Path) -> list[Path]:
    """Yield all .py files under target that are not in the exempt list.

    Test files are excluded — test function names ARE the documentation.
    """
    files: list[Path] = []
    for path in sorted(target.rglob("*.py")):
        if path.name in _EXEMPT_FILENAMES:
            continue
        # Skip test files — test names document intent, not docstrings.
        if path.parts[-1].startswith("test_") or "/tests/" in path.as_posix():
            continue
        files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    """Entry point — parse arguments, run checks, report, exit."""
    args = argv if argv is not None else sys.argv[1:]

    verbose = "--verbose" in args or "-v" in args
    targets = [a for a in args if not a.startswith("-")]

    if not targets:
        print("Usage: check_comments.py <src_dir> [--verbose]")
        print("  Example: .venv/Scripts/python.exe scripts/check_comments.py src/rrr")
        return 1

    all_violations: list[_Violation] = []
    all_files: list[Path] = []

    for raw in targets:
        root = Path(raw).resolve()
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = _collect_python_files(root)
        else:
            print(f"ERROR: path not found: {raw}")
            return 1

        for path in files:
            violations = _check_file(path)
            all_violations.extend(violations)
            all_files.append(path)
            if verbose and not violations:
                print(f"  OK   {path}")

    # Group violations by file for a readable report.
    if all_violations:
        by_file: dict[Path, list[_Violation]] = {}
        for v in all_violations:
            by_file.setdefault(v.path, []).append(v)

        print(f"\nComment coverage violations ({len(all_violations)} total):\n")
        for file_path, vs in sorted(by_file.items()):
            print(f"  {file_path}")
            for v in vs:
                print(f"    Line {v.line:4d}  {v.kind}  {v.name}")
        print(
            f"\nCOMMENTS: FAIL — {len(all_violations)} violation(s) in "
            f"{len(by_file)} file(s) out of {len(all_files)} checked"
        )
        return 1

    print(
        f"COMMENTS: PASS — {len(all_files)} file(s) checked, "
        "all modules/classes/functions have docstrings"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
