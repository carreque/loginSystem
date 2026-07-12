# Research — Login System (Centralized Authentication & Authorization on AWS)

**Date:** 2026-07-12
**Author:** Research compiled for the employee-portal auth project
**Inputs:** `loginSystem.drawio.png` (architecture diagram), `Session0.md` (design-decision log)
**Purpose:** Ground the current diagram in AWS reference architectures and OWASP standards,
document how the flow works, evaluate the chosen authorization model against alternatives,
and record the security gaps and recommended next steps.

> Scope note: this is a *research/analysis* document, not an implementation plan. It captures
> what the architecture is, why the chosen model is sound, where the risks are, and what the
> defensible options are for the future extensions the brief anticipates (MFA, federation,
> WAF, auditing).

---

## 1. System under study

The project is a **centralized authentication + per-profile authorization solution for an
internal employee portal**, built on Amazon Cognito, API Gateway, Lambda, S3, CloudFront and
IAM. Three user profiles must be distinguished:

- `empleado general` (general employee)
- `supervisor`
- `administrador` (administrator)

### 1.1 Components (as drawn)

| Component | Role in the system |
|---|---|
| **Amazon Cognito (User Pool)** | Identity provider. Authenticates the user and issues JWTs. Holds the three **User Pool Groups** (`empleado` / `supervisor` / `admin`). |
| **API Gateway** | The protected front door. Runs two authorizers: a **Cognito (JWT) authorizer** (coarse) and a **Lambda authorizer** (group-based, fine-grained). |
| **Lambda: `getResource`** | `GET /resource/{id}` — reads a resource; assumes `get-resource-role` (`s3:getObject` + logs). |
| **Lambda: `CreateUser`** | `POST /createUser` — admin console; calls `cognito-idp:AdminCreateUser`; assumes `create-user-role`. |
| **Lambda: `UploadToS3`** | `POST /upload` — writes a resource; assumes `create-resource-role` (`s3:putObject` + logs). |
| **Lambda Authorizer** | Validates the JWT (JWKS) and reads the `cognito:groups` claim to allow/deny per route. |
| **S3** | Object storage for resources. |
| **CloudFront** | CDN / cache in front of S3 for read paths. |
| **CloudWatch Logs** | Execution logging for all Lambdas. |
| **IAM roles** | Lambda **execution** roles (service permissions) — explicitly *not* the employee permission model. |

### 1.2 The two-layer authorization model (chosen in Session 0)

- **Coarse (authentication + token validity):** a Cognito User Pool Authorizer on API Gateway
  validates the JWT signature and expiry. Nothing custom.
- **Fine-grained (per-profile):** a Lambda Authorizer reads the `cognito:groups` claim and
  allows/denies per route:
  - `GET /resource/{id}` (general docs): `empleado`, `supervisor`, `admin`
  - operational resources: `supervisor`, `admin`
  - `POST /createUser` (admin console): `admin` only

This is the canonical AWS pattern: **"Start with the Cognito authorizer for simplicity, and
move to a Lambda authorizer when you need group-based access control or external data
lookups."** The design matches the reference architecture exactly.

---

## 2. How the flow works (verified against AWS reference)

```
1. Login        User ──▶ Cognito User Pool        → returns ID + Access + Refresh tokens (JWT)
2. Call API     User ──▶ API Gateway              → Authorization: Bearer <access token>
3a. Coarse      API GW  → Cognito JWT Authorizer  → validate signature (RS256) + expiry + aud
3b. Fine        API GW  → Lambda Authorizer       → read cognito:groups, allow/deny per route
4. Execute      API GW  → getResource/UploadToS3/CreateUser (only if allowed)
5. Data plane   Lambda  → S3 (get/put) / CloudFront (cached reads) / Cognito (AdminCreateUser)
6. Logging      Lambda  → CloudWatch Logs
```

The key correctness point (already fixed in Session 0): **Cognito does not forward requests to
API Gateway.** The user authenticates with Cognito, receives tokens, then calls API Gateway
*directly* with the token. The old `Cognito → API Gateway` arrow was architecturally wrong.

### 2.1 The three tokens

| Token | Contents | Default lifetime | Use in this system |
|---|---|---|---|
| **ID token** | User profile claims (email, name, `cognito:groups`) | 1 hour | Identifies the user to the app; not the primary API-auth token. |
| **Access token** | Scopes + `cognito:groups`; intended for API authorization | 1 hour (configurable 5 min – 24 h) | **The token to send to API Gateway.** Group claims map to request context for RBAC. |
| **Refresh token** | Opaque, encrypted (client cannot decode) | 30 days (configurable 60 min – 10 yr) | Silently mints new ID/Access tokens without re-login. |

**Best-practice note on token choice:** prefer the **access token** for API authorization —
its claims are the ones that map to request context for RBAC. The ID token is designed to
identify the user to the application, not to authorize API calls. (Caveat: when an ID token
passes through some authorizer integrations, the `cognito:groups` values may be delivered
comma-separated rather than as an array — one more reason to standardize on the access token.)

### 2.2 JWT verification (what the authorizers must do)

Cognito signs Access/ID tokens with **RS256** (RSA + SHA-256). Any verifier (the Cognito
authorizer does this natively; a Lambda authorizer must do it explicitly) must:

1. Fetch the public keys from the User Pool **JWKS** endpoint and match the token's `kid`.
2. **Verify the signature.**
3. Verify the token is **not expired** (`exp`).
4. Verify the **audience** (`aud` / `client_id`) matches the app client.
5. Verify the issuer (`iss`) is the expected User Pool.

Because JWKS keys rotate rarely, **cache the public keys locally** rather than fetching per
request (latency + availability). Only refresh on an unknown `kid`.

---

## 3. Security analysis (OWASP Top 10:2025 mapping)

| OWASP | Relevance to this system | Status / recommendation |
|---|---|---|
| **A01 Broken Access Control** | The core deliverable. Per-route group checks in the Lambda authorizer. | **Deny-by-default** in the authorizer: unknown route/group → deny. Enforce group checks server-side (authorizer *and* ideally a defense-in-depth check in the Lambda), never trust the client. Verify `POST /createUser` is admin-only. |
| **A02 Security Misconfiguration** | API Gateway, Cognito, S3, CloudFront defaults. | S3 bucket **not public** (serve reads via CloudFront/OAC only). Disable unused Cognito grant types. Lock CORS to the portal origin. |
| **A04 Cryptographic Failures** | JWT validation, TLS, token storage. | RS256 signature verified on every call. TLS everywhere. Store tokens securely client-side; never log tokens. |
| **A05 Injection** | `resource/{id}` path param, upload payloads. | Validate `{id}` (allowlist/format). Validate/size-limit uploads before `s3:putObject`. |
| **A06 Insecure Design** | Rate limiting, threat model. | Add API Gateway throttling / usage plans; rate-limit the login and token endpoints. |
| **A07 Authentication Failures** | Login, password policy, MFA, breached passwords. | Enforce ≥12-char passwords, Cognito password policy, and **MFA for admin/supervisor** (see §5). Use the OAuth **authorization-code grant, never implicit**. |
| **A09 Logging & Alerting Failures** | CloudWatch is present for execution logs. | Execution logs ≠ security audit trail. Add **CloudTrail** for `AdminCreateUser` and admin actions; alarm on authorizer denies / anomalous logins (see §5.4). |
| **A10 Mishandling Exceptional Conditions** | Authorizer failure behavior. | **Fail closed**: if the Lambda authorizer errors, deny (return no `Allow` policy), never fall through to allow. |

### 3.1 IAM roles vs. employee permissions (a recurring point of confusion)

The IAM roles in the diagram (`get-resource-role`, `create-user-role`, `create-resource-role`)
are **Lambda execution roles** — service-to-service permissions (Lambda → S3/logs/Cognito).
They are **not** the employee permission model. Employee profiles are an
**application-level concern** expressed through **Cognito groups + the Lambda authorizer**.
Keeping these two separate is essential; conflating them is the classic misread of this design
(and was explicitly called out with a legend note in Session 0). Each execution role should
follow **least privilege** — only the exact S3/Cognito/logs actions the function needs.

---

## 4. Authorization approach — comparison of options

The system correctly chose **Cognito authorizer (coarse) + Lambda authorizer (groups)**. For
completeness, here is how that sits against the alternatives AWS documents:

| Approach | Fine-grained? | Custom code | Best when |
|---|---|---|---|
| **Cognito User Pool Authorizer only** | No (signature/expiry only) | None | Any authenticated user may call; no per-role rules. Too coarse for this brief. |
| **Cognito + Lambda Authorizer reading `cognito:groups`** ✅ *(chosen)* | Yes (per route/group) | Moderate | RBAC by group, custom claims, or DB lookups. **Fits this project.** |
| **Cognito Identity Pool → IAM role → IAM Authorizer** | Yes (via IAM) | Low–moderate | You want AWS-native, IAM-policy-based access to AWS resources directly. |
| **Amazon Verified Permissions (Cedar) via Lambda Authorizer** | Yes (policy-as-code, attribute-based) | Moderate | Authorization logic is complex/growing, needs to be externalized from code, or ABAC (owner, MFA-present, time, resource attributes). A natural evolution path. |

**Evolution note:** If per-route `cognito:groups` checks grow into richer rules (e.g.
"a supervisor may delete a resource only if they own it *and* MFA is present"), **Amazon
Verified Permissions** externalizes that into Cedar policies evaluated by the same Lambda
authorizer — AWS provides a setup wizard that wires a Cognito User Pool to an API Gateway REST
API and secures resources by group membership. This is the recommended path *if and when* the
group-string checks become unwieldy; the current group-based model is correct for the stated
scope.

---

## 5. Future extensions (anticipated by the brief)

The brief explicitly names these as future-ready design goals. None are required for the
current scope, but the architecture should not preclude them.

### 5.1 MFA
Cognito supports TOTP and SMS MFA, plus **adaptive authentication** (risk-based). Recommend
**mandatory MFA for `admin` and `supervisor`**, optional/step-up for `empleado`. MFA state can
be surfaced as a token/context attribute and enforced in the authorizer (e.g. Verified
Permissions can require `context.mfa == true` for sensitive actions like resource deletion).

### 5.2 External federation (Google / Microsoft)
Cognito User Pools support external IdPs (SAML/OIDC — Google Workspace, Microsoft Entra ID).
Federated users can be mapped into the same three Cognito groups, so **the authorizer logic is
unchanged** — federation is additive. This is a strong argument for keeping authorization keyed
on `cognito:groups` rather than on the IdP.

### 5.3 WAF
Attach **AWS WAF** to API Gateway (and optionally CloudFront) for rate-based rules, common
attack signatures, and geo/IP allowlists. AWS also documents fronting the Cognito hosted UI
with WAF and using an injected custom header + allowlist rule so only the API Gateway proxy can
reach Cognito.

### 5.4 Access auditing / audit trail
CloudWatch currently captures **execution** logs. A real **audit trail** needs:
- **CloudTrail** for control-plane events (esp. `cognito-idp:AdminCreateUser`, group changes).
- Cognito **user activity / advanced security** logs for sign-in events.
- Structured, centralized logs with **alerting** on authorizer denials, failed logins, and
  privilege-sensitive actions (closes OWASP A09).

---

## 6. Gaps & recommended next steps

Ordered by priority:

1. **Confirm access-token-based authorization** end to end (not ID token) so `cognito:groups`
   maps cleanly to request context.
2. **Make the Lambda authorizer fail-closed** and deny-by-default for unknown routes/groups.
3. **Least-privilege the three execution roles** — scope each to only the S3/Cognito/logs
   actions it uses; nothing broader.
4. **Lock down S3** (private bucket, CloudFront Origin Access Control; no public read).
5. **Add API Gateway throttling / usage plans** and rate-limit auth endpoints (A06).
6. **Add a real audit trail** (CloudTrail + Cognito sign-in logs + alerting) beyond execution
   logs (A09).
7. **Plan MFA for privileged groups** and the authorization-code OAuth grant (A07).
8. **Keep the future band (MFA / federation / WAF / auditing) documented** as a greyed-out
   layer so reviewers see the roadmap without confusing it with current scope.
9. **Consider Amazon Verified Permissions** as the migration target *only when* group-string
   checks outgrow the Lambda authorizer.

---

## 7. Key takeaways

- The diagram, after the Session 0 fixes, is an **accurate representation of the canonical AWS
  auth architecture**: login → JWT → direct API call with Bearer token → coarse Cognito
  authorizer + fine-grained Lambda authorizer on `cognito:groups`.
- The chosen **Cognito + Lambda-authorizer group model is the correct, AWS-recommended pattern**
  for per-profile RBAC at this scope.
- The main **remaining work is hardening, not redesign**: fail-closed authorizer,
  least-privilege roles, private S3, throttling, a genuine audit trail, and MFA for privileged
  roles.
- **IAM execution roles ≠ employee permissions** — this distinction must stay explicit in every
  artifact.

---

## Sources

- [Control access to REST APIs using Amazon Cognito user pools as an authorizer — API Gateway docs](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-integrate-with-cognito.html)
- [Accessing resources with API Gateway after sign-in — Amazon Cognito docs](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-accessing-resources-api-gateway-and-lambda.html)
- [Building fine-grained authorization using Amazon Cognito, API Gateway, and IAM — AWS Security Blog](https://aws.amazon.com/blogs/security/building-fine-grained-authorization-using-amazon-cognito-api-gateway-and-iam/)
- [How to secure API Gateway HTTP endpoints with JWT authorizer — AWS Security Blog](https://aws.amazon.com/blogs/security/how-to-secure-api-gateway-http-endpoints-with-jwt-authorizer/)
- [Building well-architected serverless applications: Controlling serverless API access (part 3) — AWS Compute Blog](https://aws.amazon.com/blogs/compute/building-well-architected-serverless-applications-controlling-serverless-api-access-part-3/)
- [Understanding user pool JSON web tokens (JWTs) — Amazon Cognito docs](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html)
- [Understanding the access token — Amazon Cognito docs](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Refresh tokens — Amazon Cognito docs](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html)
- [Decode and verify the signature of a Cognito JSON Web Token — AWS re:Post](https://repost.aws/knowledge-center/decode-verify-cognito-json-token)
- [Role-based access control using Amazon Cognito and an external identity provider — AWS Security Blog](https://aws.amazon.com/blogs/security/role-based-access-control-using-amazon-cognito-and-an-external-identity-provider/)
- [Using Cognito groups to control access to API endpoints — DEV Community](https://dev.to/aws-builders/using-cognito-groups-to-control-access-to-api-endpoints-346g)
- [Authorize API Gateway APIs using Amazon Verified Permissions with Amazon Cognito — AWS Security Blog](https://aws.amazon.com/blogs/security/authorize-api-gateway-apis-using-amazon-verified-permissions-and-amazon-cognito/)
- [Authorization with Amazon Verified Permissions — Amazon Cognito docs](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-authorization-with-avp.html)
- [OWASP Top 10:2025](https://owasp.org/Top10/)
