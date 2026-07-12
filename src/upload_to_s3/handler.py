"""POST /upload -> writes an object to S3 (s3:PutObject).

Allowed groups: supervisor, admin. Enforces size + content-type limits before
upload and re-checks the caller's groups. Scaffolding only — Phase 3.
"""


def handler(event, context):  # noqa: ARG001
    raise NotImplementedError("Phase 3: size/type limits, group re-check, s3:PutObject")
