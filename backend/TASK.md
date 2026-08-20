# TASK.md — Global Project Task Tracker

## Progress

Total: 36 Tasks  
Completed: 25 Tasks (TASK-001 → TASK-025)  
Pending: 11 Tasks (TASK-026 → TASK-036)  

Current Phase: PHASE 3 — ADMIN MANAGEMENT  
Previous Phase: PHASE 2 — AUTHORIZATION & RBAC (COMPLETED)  

Current Task: TASK-026 — Admin Shared Schemas, Canonical Authorization Matrix & DB Verification  

---

## Task Details

---

### 🟢 PHASE 1: AUTHENTICATION FOUNDATION (TASK-001 → TASK-017) [COMPLETED]

#### TASK-001 — Repository & Architecture Audit
- [x] Inspect directory structure and architecture layers
- [x] Verify FastAPI app entrypoint (`app/main.py`)
- [x] Verify Async SQLAlchemy 2.0 database setup (`app/db/session.py`)
- [x] Verify Redis connection management (`app/core/redis.py`)
- [x] Audit configuration settings and environment variables

#### TASK-002 — Authentication Foundation
- [x] Configure `pyproject.toml` dependencies (`fastapi`, `sqlalchemy`, `redis`, `PyJWT`, `argon2-cffi`, `pyotp`)
- [x] Setup `.env` and `.env.example`
- [x] Define Async SQLAlchemy ORM models (`User`, `Organization`, `Session`, `PasswordHistory`)
- [x] Create Alembic migration setup (`app/db/migrations/versions/001_initial_auth.py`)
- [x] Verify database session factory and model creation unit tests

#### TASK-003 — Password Security
- [x] Implement Argon2id password hashing (`hash_password`, `verify_password`)
- [x] Enforce password strength validation (min 12 chars, uppercase, lowercase, digit, special char)
- [x] Implement password history tracking and 5 historical password reuse prevention
- [x] Implement cryptographically secure opaque token generation and SHA-256 token hashing
- [x] Ensure timing-safe hash comparison (`hmac.compare_digest`) and non-exposure in logs

#### TASK-004 — JWT / Access Token
- [x] Implement RS256 JWT creation (`create_access_token`) and verification (`decode_access_token`)
- [x] Load RSA private and public keys safely from files
- [x] Enforce algorithm restriction `algorithms=["RS256"]`
- [x] Verify required claims (`sub`, `jti`, `org`, `role`, `perms`, `mfa`, `exp`, `iss`, `aud`, `iat`, `nbf`)
- [x] Write unit tests for expired token, invalid signature, wrong issuer/audience, and malformed JWTs

#### TASK-005 — Login Endpoint
- [x] Implement `POST /api/v1/auth/login` endpoint
- [x] Perform email normalization (`strip().lower()`) and user lookup
- [x] Verify credentials using Argon2id
- [x] Check user account status (`is_active`, `is_effectively_locked`, `organization.is_active`)
- [x] Implement MFA challenge branch (HTTP 202 Accepted with `mfa_temp_token`)
- [x] Issue RS256 JWT access token and set HTTP-only, Secure, SameSite refresh token cookie
- [x] Protect against user enumeration with generic error (`AUTH_001`)

#### TASK-006 — Current User & Auth Dependency
- [x] Implement `GET /api/v1/auth/me` endpoint
- [x] Implement `aktif_kullanici()` authentication dependency in `app/api/deps.py`
- [x] Validate Bearer token signature, expiration, issuer, audience, and Redis JTI blacklist
- [x] Implement RBAC permission dependency `izin_gerektir()` and role dependency `rol_gerektir()`
- [x] Implement ABAC organization isolation (`kurum_izolasyonu_kontrolu`) and resource ownership (`sahip_veya_admin_kontrolu`)

#### TASK-007 — Refresh Token
- [x] Implement `POST /api/v1/auth/refresh` endpoint
- [x] Extract opaque refresh token from HTTP-only cookie
- [x] Lookup active session by SHA-256 token hash in database
- [x] Verify session validity (not revoked, not expired) and user active status
- [x] Implement Token Rotation (revoke old session, generate new opaque refresh token, store new session)
- [x] Issue new RS256 access token and set new HTTP-only refresh cookie
- [x] Enforce replay protection (reject reused or revoked refresh tokens)

#### TASK-008 — Logout
- [x] Implement `POST /api/v1/auth/logout` endpoint returning HTTP 204 No Content
- [x] Add access token JTI to Redis blacklist with remaining lifetime TTL
- [x] Revoke active refresh session in database (enforce user isolation)
- [x] Clear HTTP-only refresh cookie
- [x] Implement audit event abstraction (`CIKIS`)
- [x] Write integration tests for logout flow, blacklisting, cookie clearing, and idempotency

#### TASK-009 — Logout All
- [x] Implement `POST /api/v1/auth/logout-all` endpoint returning HTTP 204 No Content
- [x] Revoke ALL active refresh sessions belonging to authenticated user in database
- [x] Add current access token JTI to Redis blacklist with remaining lifetime TTL
- [x] Clear HTTP-only refresh cookie
- [x] Log audit event abstraction (`CIKIS_TUM_OTURUMLAR`)
- [x] Write integration tests for all-session invalidation, tenant isolation, cookie clearing, and distinction regression from TASK-008

#### TASK-010 — MFA Verification
- [x] Implement `POST /api/v1/auth/mfa/verify` endpoint
- [x] TOTP verification (`pyotp`) with Fernet secret decryption
- [x] Temporary login token validation (`mfa_temp_token`)
- [x] One-time token semantics (Redis lock prevents token replay)
- [x] Backup code verification & single-use consumption
- [x] Standardized `AUTH_005` error envelope on all MFA verification failures
- [x] Comprehensive test suite (`tests/test_mfa_verification.py` - 12 tests)

#### TASK-011 — Profile Update
- [x] Implement `PATCH /api/v1/auth/me` endpoint
- [x] Self-profile partial update (first_name, last_name, title, email)
- [x] Forbidden fields protection (role, permissions, org, is_active, mfa_enabled, id)
- [x] Normalized case-insensitive email uniqueness check
- [x] Comprehensive test suite (`tests/test_profile_update.py` - 17 tests)

#### TASK-012 — Change Password
- [x] Implement `POST /api/v1/auth/change-password` endpoint
- [x] Verify current password using Argon2id (`security.verify_password`)
- [x] Enforce new password strength validation (min 12 chars, uppercase, lowercase, digit, special char)
- [x] Enforce 5-password history reuse protection (`security.validate_password_not_reused`)
- [x] Record old password hash into `PasswordHistory` table
- [x] Hash new password using Argon2id and update user entity
- [x] Revoke active refresh sessions in database (`revoked_at = now`)
- [x] Log audit event `PAROLA_DEGISTIRILDI` without sensitive data
- [x] Comprehensive test suite (`tests/test_change_password.py` - 15 tests)

#### TASK-013 — Forgot Password
- [x] Implement `POST /api/v1/auth/forgot-password` endpoint
- [x] User enumeration defense (identical 200 OK response for existing & non-existing users)
- [x] Cryptographically secure 256-bit reset token generation & SHA-256 hash storage in DB
- [x] 15-minute token TTL & one-time token foundation (`used_at`)
- [x] Create `PasswordResetToken` ORM model (`app/models/password_reset_token.py`)
- [x] Email service abstraction integration (`app/services/email.py`)
- [x] Log audit event `PAROLA_SIFIRLAMA_TALEBI` without sensitive details
- [x] Comprehensive test suite (`tests/test_forgot_password.py` - 11 tests)

#### TASK-014 — Reset Password
- [x] Implement `POST /api/v1/auth/reset-password` endpoint
- [x] Verify reset token hash, expiration, and one-time use (`used_at IS NULL`)
- [x] Validate new password strength and 5-password history reuse policy
- [x] Update password hash using Argon2id and archive old hash into `PasswordHistory`
- [x] Revoke user's active database refresh sessions (`revoked_at = now`)
- [x] Log audit event `PAROLA_SIFIRLANDI` without sensitive token/password data
- [x] Comprehensive test suite (`tests/test_reset_password.py` - 14 tests)

#### TASK-015 — Session Management
- [x] Implement `GET /api/v1/auth/sessions` endpoint (list active sessions with device/IP metadata)
- [x] Implement `DELETE /api/v1/auth/sessions/{id}` endpoint (revoke specific session)
- [x] Enforce tenant isolation & IDOR protection (user can only view/revoke their own sessions)
- [x] Zero-exposure security (never expose refresh tokens or hashes in API responses)
- [x] Comprehensive test suite (`tests/test_session_management.py` - 13 tests)

#### TASK-016 — Auth Error Standardization
- [x] Existing error system audit
- [x] Standard error envelope (`code`, `message`, `detail`, `details`, `timestamp`)
- [x] `AUTH_001` mapping (invalid login credentials, wrong current password)
- [x] `AUTH_002` mapping (invalid/expired JWT Bearer token, blacklisted JTI, invalid/revoked refresh token)
- [x] `AUTH_003` mapping (RBAC/ABAC authorization failure)
- [x] `AUTH_004` mapping (account locked)
- [x] `AUTH_005` mapping (MFA required / invalid TOTP code / invalid temp token / invalid backup code)
- [x] `AUTH_006` mapping (password change required)
- [x] `VAL_001` mapping (Pydantic validation errors, password strength, password reuse)
- [x] `RATE_001` mapping (rate limit exceeded)
- [x] User enumeration audit (identical response status & error code for unknown email vs wrong password)
- [x] Dedicated auth error test suite (`tests/test_auth_error_standardization.py` - 16 tests)
- [x] Full regression test suite (234 tests passed)
- [x] Zero sensitive data leakage security audit

#### TASK-017 — Comprehensive Auth Test Matrix
- [x] Run full test matrix across all 14 auth test domains
- [x] Create unified end-to-end matrix test file (`tests/test_comprehensive_auth_matrix.py` - 10 tests)
- [x] Verify login, MFA, JWT, refresh, logout, profile, password, session, error standardization, and edge cases
- [x] Verify zero regression across all 17 canonical tasks
- [x] Achieve zero failing tests and zero warnings (244 unit/functional tests passed)

---

### 🟢 PHASE 2: AUTHORIZATION, RBAC & ABAC (TASK-018 → TASK-025) [COMPLETED]

#### TASK-018 — Role & Permission Registry Verification & Serialization
- [x] Audit existing `Role` and `Permission` enums and `ROLE_PERMISSIONS` matrix without rewriting working code
- [x] Verify full role → permission mapping coverage for all 7 system roles
- [x] Verify `get_effective_permissions()` logic `(base + extra - revoked)` and enforce conflict resolution (`revoked` ALWAYS overrides `extra`)
- [x] Support permission string normalization (`Permission.REPORT_READ` == `"report:read"`) and duplicate permission deduplication
- [x] Test unknown, invalid, or duplicate permission string behavior (raise `VAL_001` or handle gracefully)
- [x] Enforce Database Authority over JWT claims (database role/permissions are authoritative; tampered JWT claims are ignored; DB role/permission changes take immediate effect)
- [x] Verify OpenAPI schema serialization for permissions in user profile responses and JWT access tokens

#### TASK-019 — Authorization Dependencies Verification & Hardening
- [x] Audit existing `izin_gerektir(*perms)` and `rol_gerektir(*roles)` in `app/api/deps.py` without unnecessary refactoring
- [x] Enforce typed `Permission` and `Role` enum support alongside normalized string literals
- [x] Explicitly define AND/OR semantics:
  - `izin_gerektir(*perms, require_all=True)` → `Permission A AND Permission B` (Default)
  - `izin_gerektir(*perms, require_all=False)` → `Permission A OR Permission B`
  - `rol_gerektir(*roles)` → `Role A OR Role B`
- [x] Define empty permission list behavior (fail-closed / reject access with `AUTH_003`)
- [x] Enforce Database Authority inside dependencies (re-fetch/verify authoritative user state from DB via `aktif_kullanici`)
- [x] Standardize `AUTH_003` (HTTP 403 Forbidden) error envelope responses on authorization failures
- [x] Write authorization bypass and token tampering defense unit tests

#### TASK-020 — ABAC Tenant Isolation & Resource Ownership Hardening
- [x] Audit and harden existing `kurum_izolasyonu_kontrolu(user, org_id)` and `sahip_veya_admin_kontrolu(user, owner_id, org_id)`
- [x] Explicitly define `SUPER_ADMIN` bypass boundaries:
  - `SUPER_ADMIN` bypasses organization isolation boundaries (`kurum_izolasyonu_kontrolu`)
  - `SUPER_ADMIN` can access any resource via administrative override (`sahip_veya_admin_kontrolu`)
  - `SUPER_ADMIN` DOES NOT bypass authentication or explicit `Permission` requirements (`izin_gerektir`)
- [x] Define tenant boundary rules for `HOSPITAL_ADMIN`, `PHYSICIAN`, `RADIOLOGY_TECH`, `RESEARCHER`, `AUDITOR`, `SERVICE`
- [x] Prevent cross-tenant IDOR (Insecure Direct Object Reference) vulnerabilities with HTTP 403 (`AUTH_003`) responses

#### TASK-021 — Canonical Role Hierarchy & Privilege Escalation Defense
- [x] Define canonical role hierarchy:
  - Level 100: `SUPER_ADMIN` (Global Platform Admin)
  - Level 80: `HOSPITAL_ADMIN` (Tenant Admin)
  - Level 50: `PHYSICIAN`, `RADIOLOGY_TECH`, `RESEARCHER`, `AUDITOR`, `SERVICE` (Functional Roles)
- [x] Implement `can_assign_role(actor_role, target_role)` hierarchy evaluator:
  - Actor can only assign/modify roles strictly lower in rank than their own (`actor_level > target_level`)
  - `SUPER_ADMIN` can assign any role
  - `HOSPITAL_ADMIN` can only assign functional roles (`PHYSICIAN`, etc.) within their own organization
  - `HOSPITAL_ADMIN` cannot assign `SUPER_ADMIN` or `HOSPITAL_ADMIN`
  - Functional Level 50 roles (`PHYSICIAN`, `AUDITOR`, etc.) cannot assign any role
- [x] Enforce self-role escalation prevention (users cannot elevate their own role rank)

#### TASK-022 — Granular Permission Override Management API & Rules
- [x] Audit and implement management rules for `extra_permissions` and `revoked_permissions`
- [x] Enforce authorization rules for permission overrides:
  - Only `SUPER_ADMIN` or `HOSPITAL_ADMIN` (within own organization) can grant/revoke permissions
  - Self-grant protection: Detect `current_user.id == target_user_id`; admins cannot grant themselves permissions that escalate their hierarchy rank
  - Hierarchy escalation restriction: Custom permission grants cannot assign system-level admin permissions (`user:lock`, `role:assign`, `system:config`) to non-admin roles
  - Cross-organization permission overrides are strictly forbidden
- [x] Enforce conflict resolution rule: If a permission exists in both `extra_permissions` and `revoked_permissions`, `revoked_permissions` WINS (revocation takes absolute precedence)

#### TASK-023 — Comprehensive Audit Logging for Authorization & Privilege Changes
- [x] Expand audit event definitions in `app/core/audit.py`:
  - `ROL_ATANDI` / `ROLE_GRANTED`
  - `ROL_KALDIRILDI` / `ROLE_REVOKED`
  - `YETKI_ATANDI` / `PERMISSION_GRANTED`
  - `YETKI_KALDIRILDI` / `PERMISSION_REVOKED`
  - `YETKISIZ_ISLEM_GIRISIMI` / `UNAUTHORIZED_ATTEMPT` (Log blocked privilege escalation / unauthorized role assignment attempts)
- [x] Record required audit payload metadata: `actor_id`, `target_user_id`, `organization_id`, `old_value`, `new_value`, `reason`, `ip_address`, `user_agent`, `timestamp`
- [x] Enforce zero sensitive data leakage policy (never log passwords, tokens, or encryption keys in audit details)

#### TASK-024 — Sensitive Clinical & AI Action Authorization Rules (RBAC + ABAC Pipeline)
- [x] Define 5-tier evaluation pipeline: `Auth (aktif_kullanici) → Permission (izin_gerektir) → Role (rol_gerektir) → Org (kurum_izolasyonu_kontrolu) → Scope/Owner (sahip_veya_admin_kontrolu)`
- [x] Enforce Policy Precedence Rule: Explicit Role Exclusion > Extra Permission Override (e.g. `AUDITOR` with `extra_permissions = ["report:sign"]` is blocked by strict medical role policy)
- [x] Enforce `report:sign` and `report:approve` rules: Restricted strictly to `PHYSICIAN` role within matching organization assigned to the specific case
- [x] Enforce `ai:override` rules: Restricted strictly to `PHYSICIAN` role within assigned case scope
- [x] Enforce `patient:read_anonymized` rules: Authorization grants access to anonymized scope; de-identification data transformation layer strips PHI for `RESEARCHER` and `SERVICE` roles

#### TASK-025 — Combinatorial Security & RBAC Test Matrix
- [x] Build unified combinatorial test matrix suite (`tests/test_rbac_matrix.py`)
- [x] Differentiate 403 Forbidden vs 422/400 Validation Error:
  - Missing/Unassigned Runtime Permission → 403 Forbidden (`AUTH_003`)
  - Invalid Permission Enum/Schema Payload → 422 Unprocessable Entity (`VAL_001`)
- [x] Test matrix scenarios:
  - Valid permission → 200 OK
  - Missing permission → 403 Forbidden (`AUTH_003`)
  - Invalid role → 403 Forbidden
  - Cross-organization access → 403 Forbidden
  - Unowned resource access → 403 Forbidden
  - `SUPER_ADMIN` cross-org access → 200 OK
  - Admin → `SUPER_ADMIN` escalation attempt → 403 Forbidden
  - Admin self-permission grant attempt → 403 Forbidden
  - Revoked permission attempt → 403 Forbidden
  - Extra permission granted → 200 OK
  - Extra + Revoked conflict → 403 Forbidden (Revoked wins)
  - Invalid permission payload → 422 / 400 Validation Error (`VAL_001`)
  - JWT claim manipulation attempt → 401 / 403 (DB authoritative)
  - Expired JWT Bearer token → 401 Unauthorized (`AUTH_002`)
- [x] Verify zero regression across all 17 Authentication tasks and 8 RBAC tasks

---

### 🟡 PHASE 3: ADMIN MANAGEMENT ROADMAP (TASK-026 → TASK-036) [PENDING]

#### TASK-026 — Admin Shared Schemas, Canonical Authorization Matrix & DB Verification
- [ ] Inspect existing `User`, `Organization`, `Session`, `AuditLog` ORM models to verify if schema fields are sufficient for lifecycle status (`is_locked`, `locked_until`, `failed_login_attempts`, `is_active`, `deactivated_at`, `password_change_required`). Do NOT assume migrations are unnecessary without empirical verification.
- [ ] Establish the Canonical Admin Authorization Matrix defining required role, required permission, tenant scope, ownership rules, hierarchy rules, self-modification rules, audit events, expected error codes, and fail-closed behaviors for all Admin endpoints.
- [ ] Create `AdminUserResponse`, `AdminUserListResponse`, `AdminUserCreateRequest`, `AdminUserUpdateRequest` Pydantic DTOs in `app/schemas/admin.py`.
- [ ] Create `AdminOrganizationResponse`, `AdminOrganizationCreateRequest`, `AdminOrganizationUpdateRequest` schemas.
- [ ] Create `AdminSessionResponse`, `AdminAuditLogQuery`, `AdminDashboardMetricsResponse` schemas.
- [ ] Implement shared pagination query dependency `PaginationParams(page=1, page_size=20, max_page_size=100)`.
- [ ] Verify zero sensitive field exposure (`password_hash`, `mfa_secret`, `backup_codes`) in all Admin schemas.

#### TASK-027 — Admin User Directory Listing, Search & Pagination API
- [ ] Implement `GET /api/v1/admin/users` endpoint in `app/api/v1/admin.py`.
- [ ] Add query parameters: `page`, `page_size`, `search` (email, first_name, last_name), `role`, `organization_id`, `is_active`, `is_locked`.
- [ ] Enforce `rol_gerektir(Role.SUPER_ADMIN, Role.HOSPITAL_ADMIN)` authorization and `user:list` permission.
- [ ] Enforce tenant isolation (`HOSPITAL_ADMIN` only sees users in `actor.organization_id`; `SUPER_ADMIN` sees all orgs).
- [ ] Write unit & integration tests for user listing, pagination, text search, role filtering, and tenant boundary enforcement (`tests/test_admin_user_management.py`).

#### TASK-028 — Administrative User Creation & Profile Detail Management API
- [ ] Implement `POST /api/v1/admin/users` for direct user onboarding with secure initial credential generation and mandatory password change flag (`AUTH_006`).
- [ ] Implement `GET /api/v1/admin/users/{user_id}` for target user profile detail retrieval.
- [ ] Implement `PATCH /api/v1/admin/users/{user_id}` for target user profile update.
- [ ] Enforce Argon2id password hashing for new account initial credentials.
- [ ] Enforce hierarchy rank check (`can_assign_role`) preventing `HOSPITAL_ADMIN` from creating `SUPER_ADMIN` or `HOSPITAL_ADMIN` users during onboarding.
- [ ] Write unit tests for direct user onboarding, profile updates, cross-tenant rejection, and rank escalation prevention.

#### TASK-029 — Admin Role Assignment & Rank Hierarchy API
- [ ] Implement `PUT /api/v1/admin/users/{user_id}/role` endpoint.
- [ ] Enforce `rol_atamasi_kontrolu(actor, target_user, new_role)` dependency.
- [ ] Reject self-role modification (`actor.id == target_user.id` -> HTTP 403 `AUTH_003`).
- [ ] Reject rank escalation (`actor_level <= target_level` or `actor_level <= current_target_level` -> HTTP 403 `AUTH_003`).
- [ ] Reject cross-tenant role modification for `HOSPITAL_ADMIN`.
- [ ] Write unit tests for valid role transitions, self-escalation attempts, rank escalation attempts, and cross-tenant attempts.

#### TASK-030 — Target User Lifecycle Governance API (Lock, Unlock, Activate, Deactivate & Force Logout)
- [ ] Explicitly distinguish between `LOCK` (account security lock), `UNLOCK`, `DEACTIVATE` (administrative status toggle), `ACTIVATE`, and `FORCE LOGOUT` (remote session revocation).
- [ ] Implement `POST /api/v1/admin/users/{user_id}/lock` and `/unlock` endpoints (mutating `is_locked` / `locked_until`).
- [ ] Implement `POST /api/v1/admin/users/{user_id}/activate` and `/deactivate` endpoints (mutating `is_active`).
- [ ] Implement `POST /api/v1/admin/users/{user_id}/force-logout` endpoint (revoking all active sessions in DB & Redis blacklist).
- [ ] Prevent self-locking, self-deactivation, or self-force-logout.
- [ ] Write unit tests for account locking (`AUTH_004` HTTP 423), activation toggle, and force-logout invalidation.

#### TASK-031 — Multi-Tenant Organization Management API
- [ ] Implement `GET /api/v1/admin/organizations` and `POST /api/v1/admin/organizations` endpoints.
- [ ] Implement `GET /api/v1/admin/organizations/{org_id}` and `PATCH /api/v1/admin/organizations/{org_id}` endpoints.
- [ ] Implement `POST /api/v1/admin/organizations/{org_id}/activate` and `/deactivate` endpoints.
- [ ] Restrict organization creation and deactivation strictly to `SUPER_ADMIN`.
- [ ] Restrict `HOSPITAL_ADMIN` to viewing and updating their own organization profile only.
- [ ] Write unit tests for multi-tenant org CRUD, code uniqueness validation, and tenant isolation.

#### TASK-032 — System-Wide Active Session Governance & Remote Termination API
- [ ] Explicitly distinguish `/api/v1/auth/sessions` (User managing their OWN sessions from TASK-015) vs `/api/v1/admin/sessions` (Admin inspecting & terminating OTHER users' active sessions system-wide or within org scope).
- [ ] Implement `GET /api/v1/admin/sessions` endpoint (list active sessions across organization/system).
- [ ] Implement `DELETE /api/v1/admin/sessions/{session_id}` endpoint (remote session termination).
- [ ] Filter active sessions (`is_revoked == False` and `expires_at > now()`).
- [ ] Restrict `HOSPITAL_ADMIN` to sessions belonging to users within their own organization.
- [ ] Write unit tests for active session directory, remote revocation, and cross-tenant session termination rejection.

#### TASK-033 — Security Audit Log Inspection & Search API
- [ ] Implement `GET /api/v1/admin/audit-logs` endpoint for reading and searching audit logs (distinct from logging write operations in TASK-023).
- [ ] Support query filtering: `start_date`, `end_date`, `event_type`, `user_id`, `organization_id`, `result`.
- [ ] Enforce role-based audit access policy: `SUPER_ADMIN` = global logs, `HOSPITAL_ADMIN` = own org logs, `AUDITOR` = audit scope, others = HTTP 403 Forbidden.
- [ ] Enforce strict credential sanitization: zero passwords, tokens, hashes, or MFA secrets in JSON output.
- [ ] Write unit tests for audit log querying, filtering, tenant isolation, and zero sensitive data leakage.

#### TASK-034 — Admin Security Dashboard & Metrics API
- [ ] Implement `GET /api/v1/admin/dashboard/stats` endpoint.
- [ ] Calculate aggregate metrics: `total_users`, `active_users`, `locked_users`, `total_organizations`, `active_sessions`, `denials_24h`.
- [ ] Enforce tenant scope isolation: `HOSPITAL_ADMIN` metrics are strictly scoped to `actor.organization_id`.
- [ ] Write unit tests for metric calculation accuracy and tenant scope isolation.

#### TASK-035 — Admin API Security Invariants & Fail-Closed Matrix Hardening
- [ ] Audit and harden all endpoints in `backend/app/api/v1/admin.py` against edge cases and malformed inputs.
- [ ] Validate Invariants 1 through 10 across all admin handlers.
- [ ] Enforce exact error mapping (`AUTH_003` for forbidden, `AUTH_004` for locked, `VAL_001` for validation failure).
- [ ] Write edge-case and fail-closed test suite (`tests/test_admin_hardening.py`).

#### TASK-036 — Comprehensive Admin Module Integration & Security Test Matrix
- [ ] Build unified combinatorial test matrix file (`tests/test_admin_matrix.py`).
- [ ] Test all 7 roles × all admin routes × valid/invalid tenant scopes × valid/invalid hierarchy ranks.
- [ ] Run full regression test suite (`pytest backend/tests -m "not integration"`).
- [ ] Verify zero regressions across all 292 existing tests and all 36 canonical tasks.
- [ ] Update `TASK.md` to COMPLETED for all 36 tasks.
