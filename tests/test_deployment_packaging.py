"""Every module a handler imports must actually ship with it.

`pyproject.toml` puts `src` and `src/authorizer` on `sys.path`, so the unit
tests resolve imports that the deployed artifact does not contain: a function's
zip holds only its own directory, and the layer holds only what the build step
stages into `terraform/build/layer/python`. That gap is invisible to
`terraform validate`, `terraform test` and every other test here — it only
shows up in AWS as `Runtime.ImportModuleError`.

These tests walk each handler's imports and check each one resolves somewhere
that is genuinely deployed.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO / "src"
LAYER = REPO / "terraform" / "build" / "layer" / "python"

FUNCTIONS = ["authorizer", "get_resource", "upload_to_s3", "create_user"]

# Supplied by the Lambda python3.12 runtime itself, so neither zip nor layer.
RUNTIME_PROVIDED = {"boto3", "botocore"}


def imported_roots(directory):
    """Top-level module names imported by every .py file in `directory`."""
    roots = set()
    for path in sorted(directory.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots - set(sys.stdlib_module_names) - {"__future__"} - RUNTIME_PROVIDED


def is_bundled(root, function_dir):
    """True if `root` ships in the function's own zip."""
    return (function_dir / f"{root}.py").exists() or (function_dir / root).is_dir()


def is_in_layer(root):
    """True if `root` was staged into the layer (which mounts at /opt/python)."""
    return (LAYER / f"{root}.py").exists() or (LAYER / root).is_dir()


@pytest.fixture(scope="module")
def layer_built():
    if not LAYER.is_dir():
        pytest.skip(f"layer not built yet: {LAYER.relative_to(REPO)} (see README)")


@pytest.mark.parametrize("function", FUNCTIONS)
def test_every_import_is_deployed(function, layer_built):
    function_dir = SRC / function
    missing = sorted(
        root
        for root in imported_roots(function_dir)
        if not is_bundled(root, function_dir) and not is_in_layer(root)
    )
    assert not missing, (
        f"{function} imports {missing}, which ship neither in its zip "
        f"(src/{function}/) nor in the layer (terraform/build/layer/python/). "
        f"The function will fail with Runtime.ImportModuleError in AWS."
    )


def test_shared_packages_are_staged_in_the_layer(layer_built):
    """Packages under src/ that handlers import must be copied into the layer."""
    handler_roots = set()
    for function in FUNCTIONS:
        handler_roots |= imported_roots(SRC / function)

    shared = {root for root in handler_roots if (SRC / root).is_dir()}
    not_staged = sorted(root for root in shared if not is_in_layer(root))
    assert not not_staged, f"src/ packages missing from the layer: {not_staged}"
