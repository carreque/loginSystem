"""GET /resource/{id} -> reads an object from S3 (s3:GetObject).

Allowed groups: empleado, supervisor, admin. Validates {id} and re-checks the
caller's groups (defense-in-depth). Scaffolding only — implemented in Phase 3.
"""


def handler(event, context):  # noqa: ARG001
    raise NotImplementedError("Phase 3: validate {id}, group re-check, s3:GetObject")
