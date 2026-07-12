# Session 0 — Architecture Diagram Review & Fixes

**Date:** 2026-07-09
**Project:** Sistema de autenticación para portal de empleados (AWS)
**Artifacts reviewed:** `loginSystem.drawio.png` (rendered), `loginSystem.drawio` (source)
**Outcome:** `loginSystem.drawio` modified to refocus on the auth/authorization architecture.

---

## 1. Goal of the session

Review the existing architecture diagram against the project brief (a centralized
authentication + authorization solution for an internal employee portal, built on
Amazon Cognito, API Gateway, Lambda, S3, CloudFront and IAM), identify what was
missing or wrong, and modify the `.drawio` file accordingly.

The brief requires, at minimum:

- User pool configured
- A protected app/API
- A working login flow
- **Roles/permissions differentiated by profile** — three profiles:
  `empleado general`, `supervisor`, `administrador`
- Session/token handling
- Documentation of the access flow

Future extensions the design should be ready for: external federation (Google/
Microsoft), MFA, groups/roles by area, WAF integration, access auditing.

---

## 2. What the original diagram showed

Inside a single `Region` container:

- **User** → **Cognito** → **API Gateway**
- API Gateway fanned out to three **Lambda** functions:
  - `getResource` (`GET /resource/{id}`)
  - `CreateUser` (`POST /createUser`)
  - `UploadToS3` (`POST /upload`)
- **S3** for storage, **CloudFront** in front of it for cached reads
- **CloudWatch Logs** for logging
- Three **IAM roles** (Lambda execution roles), each with an "assumes" link:
  - `get-resource-role` → `s3:getObject` + logs
  - `create-user-role` → logs only
  - `create-resource-role` → `s3:putObject` + logs

---

## 3. Analysis — problems found

The diagram was essentially a **CRUD / resource-storage architecture**. It described
Lambda execution roles (infrastructure plumbing: Lambda → S3 / logs) but said almost
nothing about the **authentication and per-profile authorization flow**, which is the
actual deliverable of the project.

Specific issues:

1. **Wrong authentication flow.** The `Cognito → API Gateway` arrow is architecturally
   incorrect — Cognito does not forward requests to API Gateway. The real flow is:
   the user authenticates with Cognito, receives JWT tokens, and then calls API Gateway
   directly with the token. That direct call path was missing.

2. **No authorization layer.** No Cognito Authorizer on API Gateway, so nothing showed
   how the JWT actually protects the API.

3. **The three user profiles were absent.** No Cognito Groups, no group-claim-based
   authorization — despite "roles/permisos diferenciados por perfil" being a core
   requirement.

4. **`CreateUser` did nothing.** Its role had only logging permissions and its arrow
   pointed nowhere, even though the Administrator profile is supposed to "administrar
   accesos básicos" (i.e. create users in the pool).

5. **Ambiguous IAM roles.** The IAM roles shown are Lambda *execution* roles, which a
   reviewer could easily confuse with the *employee permission model* (which is an
   application-level concern via Cognito groups, not IAM execution roles).

---

## 4. Decisions taken with the user

Two clarifying questions were asked before editing:

- **Diagram intent →** *"Auth architecture"*: refocus the diagram on the real
  deliverable (centralized login + per-profile authorization), keeping the resource
  Lambdas as the "protected API" example. (Not the full client-ready deliverable, and
  not just cosmetic patches.)

- **Authorization model →** *"Cognito Groups + Lambda Authorizer"*: the User Pool has
  three groups; API Gateway uses a Cognito Authorizer to validate the JWT, plus a
  Lambda Authorizer that reads the `cognito:groups` claim to allow/deny per route.

The design was presented and approved before any XML was modified.

---

## 5. Changes applied to `loginSystem.drawio`

**Authentication flow (correctness fix)**
- Removed the misleading `Cognito → API Gateway` arrow.
- Relabeled `User → Cognito` as **"1. Login → JWT tokens (ID/Access)"**.
- Added the real call path `User → API Gateway`: **"2. Call API with Bearer token"**,
  routed down the far left to avoid clutter.

**Authorization layer (the missing deliverable)**
- Added a new **Lambda Authorizer** function.
- `API Gateway → Lambda Authorizer`: **"3. Authorize (JWT + groups)"**.
- `Lambda Authorizer → Cognito` (dashed): **"verify JWT (JWKS) + read groups"**.
- Added a **User Pool Groups** note on Cognito: `empleado / supervisor / admin`.
- Added an **Authorizers** note on API Gateway: `Cognito (JWT) + Lambda (groups)`.

**`CreateUser` now functional**
- Added `CreateUser → Cognito`: **"cognito-idp: AdminCreateUser"**.
- Added `cognito-idp:AdminCreateUser` to `create-user-role`'s permission list.

**Documentation / clarity**
- Added a bottom **legend** describing the auth model and the per-route → group mapping:
  - `GET /resource/{id}` (general docs): empleado, supervisor, admin
  - operational resources: supervisor, admin
  - `POST /createUser` (admin console): admin only
  - Explicit note: *IAM roles shown are Lambda execution roles (service permissions),
    NOT employee profiles.*
- Increased the `Region` container height (600 → 680) to fit the legend.

**Validation**
- Confirmed the resulting file is well-formed XML (74 `mxCell` nodes).

---

## 6. Intentionally left out (out of chosen scope)

Per the "auth architecture" scope selected, these were NOT added (offered as an optional
future "greyed-out" band):

- MFA
- External federation (Google / Microsoft)
- WAF integration
- Access auditing / audit trail

---

## 7. Follow-ups / notes

- Draw.io auto-routes the new orthogonal edges. The three arrows converging near Cognito
  (`login`, `verify JWT`, `AdminCreateUser`) may benefit from a small manual nudge for
  readability when the file is next opened.
- Next natural steps if the project continues: add the "future extensions" band, and/or
  move from diagram to an implementation plan (User Pool config, groups, authorizer
  Lambda, API Gateway wiring, IAM policies).
