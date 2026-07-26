# Login System — Employee Portal Auth (AWS)

Centralized **authentication + per-profile authorization** for an internal employee portal, built
on Amazon Cognito, API Gateway, Lambda, S3, CloudFront and IAM. Three profiles are distinguished:
`empleado`, `supervisor`, `admin`.

- **Design & rationale:** `docs/researchLoginSystem.md` (AWS + OWASP analysis), `Session0.md`.
- **Implementation plan:** `docs/planLoginSystem.md` (10 test-first phases).
- **Working agreements for tooling & gotchas:** `CLAUDE.md`.

> **Status:** Phases 1–9 complete — Lambda authorizer + resource functions, Cognito, IAM
> least-privilege roles, API Gateway, S3/CloudFront, observability, and the `*.tftest.hcl` native
> tests are all implemented and green (Terraform: 6 tests; pytest: 37 tests). Phase 10 is
> docs-only. Everything below runs **locally, without an AWS account**; a real `terraform apply` /
> deployment is deliberately deferred. Hardening-gap coverage: see
> `docs/hardeningStatusLoginSystem.md`.

## Layout

```
src/            Python 3.12 Lambda functions (authorizer, get_resource, upload_to_s3, create_user)
  common/       Shared helpers (importable package)
tests/          pytest suite (unit + moto-backed integration)
terraform/      Terraform IaC; terraform/tests/ holds *.tftest.hcl native tests
docs/           Research + implementation plan
```

## Lambda code — pytest

Requires Python 3.12+. Use a virtual environment:

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash);  .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt

python -m pytest                   # run the whole suite
python -m pytest tests/test_authorizer_rbac.py        # a single test file
python -m pytest -k "deny_by_default"                 # a single test by name
```

Test config (`pythonpath = ["src"]`, `testpaths = ["tests"]`) lives in `pyproject.toml`, so
handlers import as `from common.http import ...`, `import verify`, etc.

## Infrastructure — Terraform

Requires Terraform >= 1.9 (for `terraform test`).

**Build the shared Lambda layer first.** `lambda.tf` packages the shared `common` package plus
PyJWT as a Lambda layer by zipping `terraform/build/layer` with an `archive_file` data source.
That data source is read **at plan time**, so the directory must exist before `terraform
validate`/`test`/`plan` — otherwise the whole plan fails with *"could not archive missing
directory: ./build/layer"*. It is a generated artifact (git-ignored), rebuilt from
`requirements.txt`:

```bash
cd terraform
python -m pip install -r ../src/common/requirements.txt -t build/layer/python   # PyJWT[crypto]
cp ../src/common/*.py build/layer/python/common/                                 # shared `common` pkg
```

Then run the config:

```bash
terraform init -backend=false      # installs providers (incl. archive); no remote state needed
terraform validate                 # static check of the config
terraform fmt -recursive -check    # HCL formatting gate (drop -check to auto-format)
terraform test                     # plan-only assertions in terraform/tests/*.tftest.hcl
```

Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` to override defaults.

> The layer wheels installed above are for your **local** platform. A real AWS deploy needs
> Linux/Python 3.12 wheels — reinstall with
> `--platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:` (or build in a
> container). Deployment is out of scope; see below.

## Future: deploying to AWS

Not part of the current workflow. When ready: configure AWS credentials, set a remote backend,
then `terraform plan` / `terraform apply`, and run live end-to-end tests (login → access token →
authorized API call). See the "out of scope (future)" section of `docs/planLoginSystem.md`.
