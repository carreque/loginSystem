# Login System — Employee Portal Auth (AWS)

Centralized **authentication + per-profile authorization** for an internal employee portal, built
on Amazon Cognito, API Gateway, Lambda, S3, CloudFront and IAM. Three profiles are distinguished:
`empleado`, `supervisor`, `admin`.

- **Design & rationale:** `docs/researchLoginSystem.md` (AWS + OWASP analysis), `Session0.md`.
- **Implementation plan:** `docs/planLoginSystem.md` (10 test-first phases).
- **Working agreements for tooling & gotchas:** `CLAUDE.md`.

> **Status:** Phase 1 (scaffolding + Terraform skeleton) complete. The Lambda functions and AWS
> resources are implemented in later phases. Everything below runs **locally, without an AWS
> account**; a real `terraform apply` / deployment is deliberately deferred.

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

```bash
cd terraform
terraform init -backend=false      # no remote state needed for validate/test
terraform validate                 # static check of the config
terraform test                     # plan-only assertions in terraform/tests/*.tftest.hcl
```

Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` to override defaults.

## Future: deploying to AWS

Not part of the current workflow. When ready: configure AWS credentials, set a remote backend,
then `terraform plan` / `terraform apply`, and run live end-to-end tests (login → access token →
authorized API call). See the "out of scope (future)" section of `docs/planLoginSystem.md`.
