# Implementation Plan — Login System (Cognito + API Gateway + Lambda, on Terraform)

## Context

The project (`C:\Users\Carlos\Desktop\loginSystem`) is a centralized authentication +
per-profile authorization system for an internal employee portal. So far it exists only as a
**design**: a draw.io diagram (`loginSystem.drawio`), a Session-0 decision log (`Session0.md`),
and an analysis doc (`docs/researchLoginSystem.md`). The research doc validated the architecture
against AWS references + OWASP Top 10:2025 and closed with **9 prioritized hardening gaps**, but
is explicitly *not* an implementation.

This plan turns that design into **deployable, test-first artifacts**: Terraform IaC + Python
Lambda code, with **pytest** for the Lambda logic and **Terraform native tests** (`.tftest.hcl`)
for the infrastructure. Per the user's direction, we build and test everything locally first; a
real AWS deployment is a **future** step and is out of scope here. The 9 hardening gaps from
research §6 are baked into the design from the start rather than bolted on later.

### Key architectural reconciliation (important)
The docs describe a "two-layer" model: a **Cognito (JWT) authorizer** (coarse) **plus** a
**Lambda authorizer** (groups). In an API Gateway **REST API a method can have only one
authorizer**. The buildable, faithful implementation is a **single Lambda REQUEST authorizer**
that performs BOTH layers: full JWT verification via JWKS (the "coarse" Cognito-authorizer job)
**and** `cognito:groups` per-route RBAC (the "fine" job). We additionally add a
**defense-in-depth group re-check inside each resource Lambda** (research §3, A01). This is the
standard, correct way to realize the intended model and is what the plan implements.

## Confirmed decisions
- **IaC:** Terraform (HCL) with native `terraform test` (`*.tftest.hcl`, `command = plan` + `assert`).
- **Lambda runtime:** Python 3.12; tests with **pytest** (+ `moto` for AWS mocks, local RSA keypair for JWT).
- **Scope:** Deployable artifacts + full test suite. **No live AWS deploy** in this plan.
- **Auth token:** standardize on the **access token** (research §2.1, gap #1).
- **Profiles/groups:** `empleado`, `supervisor`, `admin`.

## Route → group authorization matrix (single source of truth)
| Method / route        | Lambda        | Allowed groups                    |
|-----------------------|---------------|-----------------------------------|
| `GET /resource/{id}`  | `getResource` | `empleado`, `supervisor`, `admin` |
| `POST /upload`        | `uploadToS3`  | `supervisor`, `admin`             |
| `POST /createUser`    | `createUser`  | `admin` only                      |
Unknown route or missing/unmatched group → **deny** (deny-by-default). Authorizer error → **fail closed**.

---

## Proposed repository layout
```
loginSystem/
  src/
    authorizer/handler.py          # Lambda REQUEST authorizer (JWT verify + RBAC)
    authorizer/verify.py           # pure fns: verify_token(), authorize(method_arn, groups)
    get_resource/handler.py        # GET /resource/{id}  -> s3:getObject
    upload_to_s3/handler.py        # POST /upload         -> s3:putObject
    create_user/handler.py         # POST /createUser     -> cognito-idp:AdminCreateUser
    common/http.py                 # shared response/group-recheck helpers
    common/requirements.txt        # PyJWT[crypto] (or python-jose), boto3 provided by runtime
  tests/                           # pytest
    conftest.py                    # RSA keypair + fake JWKS + token factory fixtures
    test_authorizer_verify.py      # signature/exp/aud/iss, kid-miss, tampered token
    test_authorizer_rbac.py        # full route matrix incl. deny-by-default + fail-closed
    test_get_resource.py           # moto S3, group re-check, {id} validation
    test_upload_to_s3.py           # moto S3, size/type limits, group re-check
    test_create_user.py            # moto Cognito AdminCreateUser, admin-only re-check
  terraform/
    versions.tf providers.tf variables.tf outputs.tf
    cognito.tf apigateway.tf lambda.tf iam.tf s3_cloudfront.tf observability.tf
    tests/
      cognito.tftest.hcl s3.tftest.hcl apigateway.tftest.hcl iam.tftest.hcl
  README.md                        # build/test/deploy-later instructions
```
Design for isolation: authorizer logic lives in **pure functions** (`verify.py`) so JWT checks
and RBAC are unit-testable without AWS; handlers are thin adapters.

---

## Implementation phases (test-first within each)

### Phase 1 — Scaffolding & Terraform skeleton
- Create `src/`, `tests/`, `terraform/` tree; `versions.tf` (Terraform ≥1.9 for `terraform test`,
  AWS provider ~>5), `providers.tf`, `variables.tf` (region, project name, portal origin, allowed
  callback URLs, log level), `outputs.tf`.
- `README.md` with the local workflow (pytest + `terraform validate`/`test`) and a "future: deploy" section.

### Phase 2 — Lambda authorizer (TDD) — closes gaps #1, #2; OWASP A01/A04/A10
- **Write pytest first** (`test_authorizer_verify.py`, `test_authorizer_rbac.py`): generate a local
  RSA keypair in `conftest.py`, expose a fake JWKS + a token-factory fixture (mint access tokens with
  chosen `kid`/`exp`/`aud`/`iss`/`cognito:groups`). Assert: valid signature passes; wrong `kid`,
  expired, wrong `aud`, wrong `iss`, tampered payload all **deny**; full route→group matrix; unknown
  route denies; internal error path returns an explicit **Deny** policy (fail-closed).
- Then implement `verify.py`:
  - `verify_token(token, jwks, issuer, audience)` — RS256, `kid` match, `exp`, `aud`/`client_id`,
    `iss`; JWKS **cached** in module scope, refresh only on unknown `kid` (research §2.2).
  - `authorize(method_arn, groups)` — parse `httpMethod`/resource from `methodArn`, apply the matrix,
    build the IAM policy; **default deny**.
  - `handler.py` — REQUEST authorizer: read access token from `Authorization` header, call the two
    pure fns, return policy; wrap in try/except that returns Deny on any error.
- Config via env: `USER_POOL_ID`, `APP_CLIENT_ID`, `AWS_REGION`, `JWKS_URL` (overridable for tests).

### Phase 3 — Resource Lambdas (TDD) — defense-in-depth (A01), input validation (A05)
- `get_resource`: validate `{id}` against an allowlist/format regex, `s3:getObject`, re-check group
  membership from authorizer context; tests use **moto** S3.
- `upload_to_s3`: **size + content-type limits** before `s3:putObject` (A05); group re-check; moto S3.
- `create_user`: `cognito-idp:AdminCreateUser`; **admin-only** re-check; moto Cognito; validate input.
- `common/http.py`: shared JSON responses + `require_groups(event, allowed)` helper (never trust client).

### Phase 4 — Cognito (Terraform) — closes gap #7; A02/A07
- `aws_cognito_user_pool`: password policy **≥12 chars**, all char classes; advanced security
  (breached-password detection) enabled.
- MFA: **required for admin/supervisor** workflow — pool MFA `ON`/`OPTIONAL` + TOTP; document that
  step-up enforcement surfaces via token/context (research §5.1).
- Three `aws_cognito_user_group` (`empleado`/`supervisor`/`admin`).
- `aws_cognito_user_pool_client`: **authorization-code grant only, implicit disabled** (A07),
  unused OAuth flows off, callback URLs from variables, access-token lifetime configurable.

### Phase 5 — IAM least-privilege execution roles (Terraform) — closes gap #3; A01
- One role **per** Lambda, each scoped to exactly its actions (mirrors diagram names):
  - `get-resource-role`: `s3:GetObject` on the bucket ARN + logs.
  - `create-resource-role`: `s3:PutObject` on the bucket ARN + logs.
  - `create-user-role`: `cognito-idp:AdminCreateUser` on the pool ARN + logs.
  - `authorizer-role`: logs only.
- No wildcards on resources; scope to specific ARNs. (Reinforce research §3.1: execution roles ≠ employee model.)

### Phase 6 — API Gateway (Terraform) — closes gap #5; A06
- REST API with the three methods wired to the **single Lambda authorizer** (`type = REQUEST`,
  identity source = `Authorization` header).
- **Throttling / usage plan** on the stage (rate + burst limits) to rate-limit API and auth-adjacent
  paths (A06).
- Lambda permissions for API Gateway to invoke each function + the authorizer.

### Phase 7 — S3 + CloudFront (Terraform) — closes gap #4; A02
- Private `aws_s3_bucket` with **Block Public Access = all true**, default encryption, versioning.
- CloudFront distribution with **Origin Access Control (OAC)**; bucket policy allows only the CF
  distribution (no public read).

### Phase 8 — Observability & audit trail (Terraform) — closes gap #6; A09
- CloudWatch log groups per Lambda with retention.
- **CloudTrail** capturing control-plane events (esp. `AdminCreateUser`, group changes).
- CloudWatch **metric filter + alarm** on authorizer **Deny** events / failed logins (research §5.4).

### Phase 9 — Terraform native tests (`terraform/tests/*.tftest.hcl`)
`command = plan` + `assert` blocks (no apply, no AWS calls) verifying the hardening is actually coded:
- `s3.tftest.hcl`: all four public-access-block flags true; encryption on; bucket not public.
- `cognito.tftest.hcl`: password min length ≥12; implicit grant absent; auth-code flow present.
- `apigateway.tftest.hcl`: each method's `authorization = CUSTOM` + bound authorizer; throttling set.
- `iam.tftest.hcl`: each role policy contains only its expected action(s); no `"*"` resource/action.

### Phase 10 — Docs & wiring
- Update `README.md` (how to run pytest, `terraform init/validate/test`), and a short note in
  `docs/` recording that gaps #1–#7 are implemented, #8 (greyed-out future band on the diagram) and
  #9 (Verified Permissions migration) remain design-only future items.

---

## Reused / referenced inputs
- **Route matrix, role names, group names**: taken verbatim from `loginSystem.drawio` legend and
  `Session0.md` §5 so code/infra match the approved diagram exactly.
- **Hardening requirements**: `docs/researchLoginSystem.md` §3 (OWASP map) and §6 (the 9 gaps) —
  each phase above cites which gap it closes.

## Verification (end-to-end, local — no AWS account needed)
1. **Lambda logic:** `cd loginSystem && python -m pytest -q` → all unit/integration tests green
   (authorizer matrix incl. deny-by-default + fail-closed; moto-backed S3/Cognito handlers).
2. **Infra static check:** `cd terraform && terraform init -backend=false && terraform validate`.
3. **Infra behavior:** `terraform test` → all `*.tftest.hcl` asserts pass (S3 private, password ≥12,
   implicit grant off, methods use the custom authorizer, IAM least-privilege, throttling set).
4. **Plan sanity (optional, offline):** `terraform plan` with placeholder vars to confirm the graph
   resolves. Real `apply` to AWS is deferred to the future deployment step.

## Explicitly out of scope (future)
- Real AWS deployment / live end-to-end login test (future, per user).
- Diagram "future band" (MFA/federation/WAF/auditing greyed-out layer) — gap #8, doc-only.
- Amazon Verified Permissions (Cedar) migration — gap #9, only when group-string checks outgrow the authorizer.
- External IdP federation (Google/Microsoft) and WAF attachment.
