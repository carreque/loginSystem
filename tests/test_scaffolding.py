"""Phase 1 smoke test: confirms the repository scaffolding is in place.

Joined by real unit tests (authorizer, resource Lambdas) in Phase 2+.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_tree_exists():
    for pkg in ("authorizer", "get_resource", "upload_to_s3", "create_user", "common"):
        assert (ROOT / "src" / pkg).is_dir(), f"missing src/{pkg}"


def test_terraform_skeleton_exists():
    for name in ("versions.tf", "providers.tf", "variables.tf", "outputs.tf"):
        assert (ROOT / "terraform" / name).is_file(), f"missing terraform/{name}"
