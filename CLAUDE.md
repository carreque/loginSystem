# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A centralized **authentication + per-profile authorization** system for an internal employee
portal, built on AWS (Amazon Cognito, API Gateway, Lambda, S3, CloudFront, IAM). It distinguishes
three user profiles: `empleado` (general employee), `supervisor`, `admin`.

**Current state: Phase 1 complete (scaffolding + Terraform skeleton).** The repo now has a
runnable test toolchain and an empty-but-valid Terraform config; the Lambda logic and AWS
resources are still stubs (`src/**/handler.py` raise `NotImplementedError`). Work proceeds through
the phases in `docs/planLoginSystem.md`, test-first. Everything runs **locally without an AWS
account**; live deployment is deferred.

## Key artifacts (read these to get oriented)

- `docs/planLoginSystem.md` — **the approved implementation plan.** 10 test-first phases, repo
  layout, route→group matrix, and how each phase closes a specific hardening gap. Start here.
- `docs/researchLoginSystem.md` — analysis grounding the design in AWS references + OWASP
  Top 10:2025. §2 = auth flow, §2.2 = JWT verification steps, §3 = OWASP mapping, §6 = the 9
  prioritized hardening gaps the plan implements.
- `Session0.md` — decision log for the architecture diagram. §5 records the exact component/route
  names; §4 records the two approved design decisions.
- `loginSystem.drawio` (+ `.png`) — the architecture diagram. The bottom legend is the canonical
  source for the route→group matrix and role names; keep code/infra consistent with it.

## Architecture essentials (the big picture)

**Auth flow:** User → Cognito (login) → receives JWTs → calls API Gateway **directly** with
`Authorization: Bearer <access token>`. Cognito does **not** forward requests to API Gateway
(an earlier version of the diagram had this wrong — do not reintroduce it).

**Authorization is per-route by Cognito group.** The route → allowed-groups matrix (single source
of truth, from the diagram legend):

| Method / route       | Lambda        | Allowed groups                    |
|----------------------|---------------|-----------------------------------|
| `GET /resource/{id}` | `getResource` | `empleado`, `supervisor`, `admin` |
| `POST /upload`       | `uploadToS3`  | `supervisor`, `admin`             |
| `POST /createUser`   | `createUser`  | `admin` only                      |

## Non-obvious rules (easy to get wrong — enforce these)

1. **Single Lambda authorizer implements the "two-layer" model.** Docs describe a Cognito (JWT)
   authorizer *plus* a Lambda (groups) authorizer, but an API Gateway **REST** method allows only
   **one** authorizer. The buildable design is a single Lambda REQUEST authorizer that does BOTH
   full JWT verification (JWKS/RS256, `exp`, `aud`, `iss`) **and** `cognito:groups` RBAC, with a
   defense-in-depth group re-check inside each resource Lambda. See plan "Key architectural
   reconciliation."
2. **IAM execution roles ≠ the employee permission model.** The IAM roles (`get-resource-role`,
   `create-user-role`, `create-resource-role`) are Lambda **execution** roles (service-to-service:
   Lambda → S3/logs/Cognito). Employee profiles are an application concern expressed via Cognito
   groups + the authorizer. Never conflate them.
3. **Authorize on the access token, not the ID token** (its claims map to request context for RBAC).
4. **Fail closed / deny by default.** Authorizer errors or unknown route/group → return a Deny
   policy, never fall through to Allow.
5. **Never trust the client** for group membership — enforce server-side in the authorizer and
   re-check in the Lambda.

## Commands

Local-first: all of these run **without an AWS account**. Real `terraform apply` / live deployment
is deferred. See `README.md` for full setup.

**Lambda tests** (Python 3.12+; dev deps in `requirements-dev.txt` — pytest, moto, PyJWT):
```bash
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt  # first time
python -m pytest                                # whole suite
python -m pytest tests/test_authorizer_rbac.py  # a single file
python -m pytest -k "deny_by_default"           # a single test by name
```
Pytest config is in `pyproject.toml` (`pythonpath = ["src"]`, `testpaths = ["tests"]`), so handlers
import as `import verify`, `from common.http import ...`.

**Infrastructure** (Terraform >= 1.9):
```bash
cd terraform
terraform init -backend=false   # no remote state needed for validate/test
terraform fmt -recursive        # keep HCL formatted (CI-checkable with -check)
terraform validate              # static check
terraform test                  # plan-only assertions in terraform/tests/*.tftest.hcl (added Phase 9)
```

## Layout

```
src/<fn>/handler.py   Lambda entrypoints: authorizer, get_resource, upload_to_s3, create_user
src/authorizer/verify.py   (Phase 2) pure fns: verify_token(), authorize() — unit-tested in isolation
src/common/                Shared, importable package (http helpers, group re-check)
tests/                     pytest; conftest.py will hold the RSA-keypair/JWKS/token fixtures (Phase 2)
terraform/*.tf             Skeleton now (versions/providers/variables/outputs); resources added per phase
terraform/tests/           *.tftest.hcl native infra tests (Phase 9)
```

To check about conventions please take a look at @reference/conventions.md