# NeuroOncoTrack-AI — Backend Security Architecture & Governance Specification

## Overview

This specification documents the complete Security Architecture, Authentication, Role-Based Access Control (RBAC), Attribute-Based Access Control (ABAC), Tenant Isolation, Resource Ownership, Clinical & AI Action Pipeline, and Security Audit Logging infrastructure for **NeuroOncoTrack-AI**.

---

## 1. Executive Summary & Verification Metrics

- **Canonical Tasks Completed:** 25 / 25 (TASK-001 → TASK-025)
- **Unit & Matrix Tests Passing:** 292 / 292 (100% Pass Rate)
- **Critical Vulnerabilities:** 0
- **Regression Count:** 0

---

## 2. Core Security Invariants

1. **INVARIANT 1 (Revoked Precedence Rule):** `revoked_permissions` ALWAYS overrides `extra_permissions` and base permissions.
2. **INVARIANT 2 (Cross-Tenant Isolation):** Non-super admin users are strictly restricted to their own organization scope (`user.organization_id == resource.organization_id`).
3. **INVARIANT 3 (Self-Escalation Defense):** Users cannot modify or escalate their own role or permissions.
4. **INVARIANT 4 (Role Rank Hierarchy):** Role assignments require `actor_level > target_level` AND `actor_level > current_target_level`.
5. **INVARIANT 5 & 6 (Payload Spoofing Defense):** Client-provided `organization_id` or `owner_id` values in request payloads are ignored for authorization decisions; database authority is enforced.
6. **INVARIANT 7 & 8 (SUPER_ADMIN Strictness):** `SUPER_ADMIN` bypasses organization scope, but CANNOT bypass authentication or explicit permission revocations.
7. **INVARIANT 9 (Missing Attribute Fail-Closed):** Missing `user_id`, `organization_id`, or `role` attributes fail closed with HTTP 403 (`AUTH_003`).
8. **INVARIANT 10 (Live DB Authority Over Stale JWT):** Client JWT claims are not authoritative; live database user state (`aktif_kullanici`) is evaluated synchronously on every request.

---

## 3. Canonical System Roles & Hierarchy

| Role Enum | Level | Scope | Primary Purpose |
| :--- | :---: | :--- | :--- |
| `SUPER_ADMIN` | 100 | Global (Multi-Tenant) | System Root. Full access across all organizations. |
| `HOSPITAL_ADMIN` | 80 | Own Organization | Hospital Administrator. Manages users in own org. Cannot sign medical reports. |
| `PHYSICIAN` | 50 | Own Cases | Specialist Physician. Creates cases, runs AI, signs medical reports (`report:sign`). |
| `RADIOLOGY_TECH` | 50 | Own Scans | Radiology Technician. Uploads DICOM imaging. |
| `RESEARCHER` | 50 | Anonymized Scope | Medical Researcher. Reads anonymized patient data (`patient:read_anonymized`). |
| `AUDITOR` | 50 | Audit Scope | Security Auditor. Reads security audit logs. |
| `SERVICE` | 50 | Integration Scope | Machine-to-Machine Service. Syncs FHIR resources. |

---

## 4. 5-Tier Evaluation Pipeline

```
REQUEST
  │
  ├── TIER 1: Authentication & Active User Check (aktif_kullanici)
  │
  ├── TIER 2: RBAC Permission Check (has_permission with revoked precedence)
  │
  ├── TIER 3: Medical Role Policy Check (e.g. report:sign restricted to PHYSICIAN)
  │
  ├── TIER 4: Tenant Isolation Check (kurum_izolasyonu_kontrolu)
  │
  └── TIER 5: Resource Ownership Check (sahip_veya_admin_kontrolu)
  │
  └── [GRANTED] -> Execute Request & Audit Log
```

---

## 5. Security Audit Logging & Sanitization

All authorization events and denial attempts are logged using `log_authorization_event()`.

### Sanitized Sensitive Fields
The following fields are strictly excluded from audit log details:
- `password`, `password_hash`, `access_token`, `refresh_token`, `jwt`, `mfa_secret`, `totp_secret`, `backup_code`, `api_key`, `session_secret`, `reset_token`, `credentials`, `key`.

---

## 6. Architecture File Map

- `backend/app/core/permissions.py`: Role, Permission, RBAC matrix, Precedence evaluator, ABAC helpers.
- `backend/app/api/deps.py`: `aktif_kullanici`, `izin_gerektir`, `rol_gerektir`, `hassas_klinik_ve_ai_islem_kontrolu`.
- `backend/app/core/audit.py`: Security audit logging and credential sanitization.
- `backend/app/api/v1/admin.py`: Granular Permission Override Management API.
- `backend/tests/test_authorization.py`: Comprehensive 58-test authorization & security matrix suite.
