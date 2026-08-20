# NeuroOncoTrack-AI — Authentication Implementation

## ROL

Sen bu projede kıdemli bir Backend / Security Engineer olarak çalışıyorsun.

Model: **Claude Opus 4.6**

Görevin, mevcut backend mimarisini inceleyerek yalnızca **Authentication / Session Management** kapsamını adım adım implement etmektir.

Bu çalışma sırasında mimari dokümanda tanımlanmayan yeni bir authentication davranışı kendiliğinden icat etme.

Kaynak mimari:

`NeuroOncoTrack-AI_Backend_Mimari_Plani-2.html`

Bu doküman authentication için ana referanstır.

---

# ÇOK ÖNEMLİ ÇALIŞMA KURALI

## TASK-BY-TASK ÇALIŞ

Tüm sistemi tek seferde geliştirme.

Her task bağımsız bir milestone olarak ele alınacak.

Akış:

1. Mevcut kodu incele.
2. İlgili task'ın gereksinimlerini çıkar.
3. Sadece o task için gerekli değişiklikleri yap.
4. Testleri yaz / çalıştır.
5. Lint / type / import / migration problemlerini kontrol et.
6. Task'ın acceptance criteria'larını tek tek doğrula.
7. Sonuç raporu ver.
8. **DUR.**
9. Kullanıcı onay vermeden sonraki task'a geçme.

Kullanıcı "TASK-002'ye geç" veya benzeri bir onay vermeden sonraki task üzerinde hiçbir değişiklik yapma.

---

# KAPSAM

Şimdilik yalnızca:

- Authentication
- Authorization'a temel oluşturacak current-user yapısı
- Session management
- Access token
- Refresh token
- Login
- Logout
- MFA authentication flow
- Password change
- Password reset
- Current user/profile
- Session listing/revocation

implement edilecek.

## ŞİMDİLİK YAPILMAYACAKLAR

Aşağıdaki modüllere girme:

- Patients
- Studies
- AI
- Reports
- RAG
- FHIR
- Audit API'nin tamamı
- Admin user management
- Model management
- Object storage
- Celery
- Klinik iş mantığı

Ancak authentication'ın çalışması için zorunlu dependency gerekiyorsa minimum altyapısını oluşturabilirsin.

---

# MİMARİ KURALLAR

Backend:

- Python 3.11
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL 16
- Alembic
- Redis 7
- RS256 JWT
- Argon2id

Katmanlar:

```text
Router
   ↓
Service
   ↓
Repository / Data Access
   ↓
Database
```

Router içinde business logic yazma.

Authentication mantığını router'lara dağıtma.

Örneğin:

```text
POST /auth/login
        ↓
AuthRouter
        ↓
AuthService
        ↓
UserRepository
        ↓
PostgreSQL
```

Security ile ilgili ortak işlemler:

```text
app/core/security.py
```

içinde merkezi tutulmalı.

Authentication dependency:

```text
app/api/deps.py
```

üzerinden merkezi çalışmalı.

---

# AUTH ENDPOINT KATALOĞU

Base path:

```text
/api/v1
```

## 1. Login

```http
POST /api/v1/auth/login
```

Açık endpoint.

Input:

```json
{
  "email": "user@example.com",
  "password": "..."
}
```

Başarılı authentication:

- Access token
- Access token expiration
- User profile
- Role
- Permissions
- Organization
- password change requirement
- MFA status

döndürmeli.

MFA gerekiyorsa:

```text
HTTP 202
```

ve geçici authentication token dönmeli.

---

## 2. MFA Verify

```http
POST /api/v1/auth/mfa/verify
```

Geçici token + MFA code ile authentication tamamlanır.

Başarılı olduğunda normal:

- access token
- refresh token cookie
- user
- role
- permissions

akışı oluşmalı.

---

## 3. Refresh

```http
POST /api/v1/auth/refresh
```

Refresh token cookie'den alınır.

Access token yenilenir.

Refresh token rotation uygulanır.

Eski refresh token tekrar kullanılamamalı.

---

## 4. Logout

```http
POST /api/v1/auth/logout
```

Mevcut access token'ın `jti` değeri blacklist'e alınır.

Refresh session iptal edilir.

Refresh cookie temizlenir.

Response:

```text
204 No Content
```

---

## 5. Logout All

```http
POST /api/v1/auth/logout-all
```

Kullanıcının bütün aktif session'ları iptal edilir.

---

## 6. Current User

```http
GET /api/v1/auth/me
```

Authenticated user bilgilerini döndürür.

---

## 7. Update Current User

```http
PATCH /api/v1/auth/me
```

Kullanıcının yalnızca kendi profilini değiştirmesine izin ver.

---

## 8. Change Password

```http
POST /api/v1/auth/change-password
```

Mevcut parola doğrulanmadan parola değiştirilemez.

---

## 9. Forgot Password

```http
POST /api/v1/auth/forgot-password
```

Public endpoint.

Reset token oluşturulur.

Reset token:

```text
15 dakika
```

geçerlidir.

Email enumeration yapılmamalıdır.

---

## 10. Reset Password

```http
POST /api/v1/auth/reset-password
```

Reset token ile yeni parola belirlenir.

---

## 11. Sessions

```http
GET /api/v1/auth/sessions
```

Kullanıcının aktif session'larını döndürür.

---

## 12. Session Revocation

```http
DELETE /api/v1/auth/sessions/{id}
```

Belirli session sonlandırılır.

---

# TOKEN MİMARİSİ

## Access Token

JWT.

Algorithm:

```text
RS256
```

Expiration:

```text
15 minutes
```

Payload:

```json
{
  "sub": "user_id",
  "jti": "token_id",
  "org": "organization_id",
  "role": "PHYSICIAN",
  "perms": [],
  "mfa": true,
  "iat": 1750000000,
  "exp": 1750000900,
  "iss": "neurooncotrack-api",
  "aud": "neurooncotrack-web"
}
```

Access token frontend tarafından memory'de tutulur.

---

# REFRESH TOKEN

Refresh token JWT olmak zorunda değildir.

Mimaride:

```text
opaque random 256-bit token
```

kullanılmaktadır.

Expiration:

```text
7 days
```

Refresh token:

- HttpOnly
- Secure
- SameSite
- cookie

olarak kullanılmalıdır.

Database'de plaintext refresh token saklama.

Hash / digest sakla.

Her refresh kullanımında rotation yap.

Eski refresh token tekrar kullanılırsa kabul etme.

---

# PASSWORD SECURITY

Password hashing:

```text
Argon2id
```

Parametreler:

```text
memory = 64 MB
iterations = 3
parallelism = 4
```

Password:

- minimum 12 karakter
- uppercase
- lowercase
- number
- special character

gerektirir.

Ayrıca:

- leaked password kontrolü
- son 5 password reuse engeli
- first-login password change
- admin için 90 günlük password change

mimaride tanımlıdır.

Bu kuralları ilgili task geldiğinde uygula.

---

# LOGIN SECURITY

Login rate limit:

```text
5 attempts / 15 minutes / IP
```

Başarısız login:

- failed attempt counter artır
- 5. denemede account 30 dakika lock

Login sırasında:

1. rate limit
2. account status
3. organization status
4. password verification
5. failed attempt handling
6. MFA
7. session creation
8. token creation

uygulanmalı.

---

# USER ENUMERATION ENGELİ

Şu iki durum birbirinden ayırt edilmemeli:

```text
User does not exist
```

ve

```text
Wrong password
```

İkisi için aynı authentication error kullanılmalı:

```text
AUTH_001
```

Yanıt süreleri de mümkün olduğunca aynı tutulmalı.

Client'a:

```text
"Kullanıcı bulunamadı"
```

veya

```text
"Parola yanlış"
```

gibi ayrıştırıcı bilgiler verme.

---

# ERROR CONTRACT

Tüm API hataları ortak envelope kullanmalı:

```json
{
  "error": {
    "code": "AUTH_003",
    "message": "Bu işlem için yetkiniz bulunmamaktadır.",
    "detail": "Gerekli izin: report:approve",
    "request_id": "01J8X...",
    "timestamp": "ISO-8601"
  }
}
```

Authentication error kodları:

```text
AUTH_001 = 401
E-posta veya parola hatalı

AUTH_002 = 401
Jeton süresi dolmuş veya geçersiz

AUTH_003 = 403
Yetersiz izin

AUTH_004 = 423
Hesap kilitli

AUTH_005 = 401
MFA gerekli veya hatalı

AUTH_006 = 403
Parola değişimi zorunlu
```

Validation:

```text
VAL_001 = 422
```

Rate limit:

```text
RATE_001 = 429
```

---

# USER MODEL

Authentication için gerekli User alanlarını mimariye göre oluştur.

Minimum konsept:

```text
id
organization_id
email
password_hash
first_name
last_name
title
role
extra_permissions
revoked_permissions

is_active
is_locked
locked_until
failed_login_attempts

mfa_enabled
mfa_secret
backup_codes

must_change_password
password_changed_at
last_login_at

created_by
archived_at

created_at
updated_at
```

Hassas alanları plaintext olarak loglama.

MFA secret şifreli saklanmalıdır.

Backup code'lar hashlenmiş saklanmalıdır.

---

# SESSION MODEL

Session entity:

```text
id
user_id

refresh_token_hash

ip_address
user_agent
device_fingerprint

created_at
last_used_at
expires_at

revoked_at
revocation_reason
```

Refresh token'ın kendisini database'e plaintext kaydetme.

---

# REDIS

Redis authentication için özellikle:

```text
access token blacklist
login rate limiting
```

amaçlarıyla kullanılacak.

Blacklist key'leri token'ın kalan expiration süresi kadar tutulmalı.

---

# AUTH DEPENDENCY

Merkezi dependency oluştur:

```text
aktif_kullanici()
```

Bu dependency:

1. Authorization header alır
2. Bearer token çıkarır
3. JWT signature doğrular
4. issuer doğrular
5. audience doğrular
6. expiration doğrular
7. gerekli claim'leri kontrol eder
8. blacklist kontrolü yapar
9. user'ı çözer
10. inactive / locked kullanıcıyı reddeder
11. current user döndürür

Router'larda manuel token parsing yapma.

---

# PERMISSION HAZIRLIĞI

Authorization'ın tamamını şimdi geliştirme.

Ancak authentication user model ve token payload gelecekte permission sistemiyle uyumlu olmalı.

Permission formatı:

```text
resource:action
```

Örneğin:

```text
user:read
patient:read
ai:override
report:approve
```

JWT içinde `perms` claim'i bulunmalı.

---

# AUDIT

Authentication event'leri gelecekte audit sistemine bağlanabilecek şekilde service abstraction üzerinden hazırlanmalı.

Örneğin:

```text
GIRIS_BASARILI
GIRIS_BASARISIZ
CIKIS
```

Ancak bu task serisinde tüm Audit API'yi geliştirme.

---

# DOSYA ORGANİZASYONU

Mevcut repository yapısını ÖNCE incele.

Mimari dokümanda önerilen yapı:

```text
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── permissions.py
│   │   ├── exceptions.py
│   │   └── logging.py
│   ├── db/
│   │   ├── session.py
│   │   └── migrations/
│   ├── models/
│   ├── schemas/
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/
│   ├── services/
│   └── middleware/
└── tests/
```

Mevcut proje farklıysa körü körüne yeniden yapılandırma.

Önce mevcut yapıyı analiz et.

Mümkün olduğunca mevcut mimariye uy.

---

# TASK PLANI

## TASK-001 — Repository & Architecture Audit

Amaç:

Mevcut backend'i incelemek.

Yapılacaklar:

- directory structure
- FastAPI app entrypoint
- database setup
- SQLAlchemy setup
- Alembic
- Redis
- config
- existing models
- existing auth code
- existing middleware
- existing tests
- existing dependencies

incele.

Henüz authentication implement etme.

Çıktı:

```text
CURRENT ARCHITECTURE
AUTH EXISTING COMPONENTS
MISSING COMPONENTS
CONFLICTS
RECOMMENDED IMPLEMENTATION ORDER
```

Sonra DUR.

---

## TASK-002 — Authentication Foundation

Oluştur / düzelt:

- config
- security module
- exception types
- auth schemas
- User model
- Session model
- migrations

Henüz login endpoint implement etme.

Test:

- model creation
- migration
- password hashing helper
- token helper temel testleri

Sonra DUR.

---

## TASK-003 — Password Security

Implement:

- Argon2id
- password validation
- password verification
- password reuse foundation
- secure random token generation
- token hashing

Testleri yaz.

Login endpointine geçme.

Sonra DUR.

---

## TASK-004 — JWT / Access Token

Implement:

```text
RS256
```

JWT:

- signing
- verification
- claims
- issuer
- audience
- expiration
- jti

Test:

- valid token
- expired token
- invalid signature
- invalid issuer
- invalid audience
- missing claim
- malformed token

Sonra DUR.

---

## TASK-005 — Login Endpoint

Implement:

```http
POST /api/v1/auth/login
```

Tam login flow:

- rate limit
- user lookup
- account status
- organization status
- password verification
- failed attempts
- account lock
- MFA branch
- access token
- refresh session
- cookie
- last login
- response

Test:

- valid login
- wrong password
- unknown email
- locked user
- inactive user
- inactive organization
- rate limit
- MFA enabled
- first password change requirement

Sonra DUR.

---

## TASK-006 — Current User

Implement:

```http
GET /api/v1/auth/me
```

ve:

```text
aktif_kullanici()
```

dependency.

Test:

- valid token
- expired token
- invalid token
- blacklisted token
- inactive user
- locked user
- missing Authorization

Sonra DUR.

---

## TASK-007 — Refresh Token

Implement:

```http
POST /api/v1/auth/refresh
```

Requirements:

- HttpOnly cookie
- refresh token hash
- session lookup
- expiration
- revoked check
- rotation
- old token invalidation
- new access token
- new refresh cookie

Test özellikle:

```text
same refresh token twice
```

ikinci kullanım kesinlikle reddedilmeli.

Sonra DUR.

---

## TASK-008 — Logout

Implement:

```http
POST /api/v1/auth/logout
```

Requirements:

- access token blacklist
- refresh session revoke
- cookie clear
- audit abstraction
- 204 response

Test:

```text
logout
old access token
old refresh token
cookie
```

Sonra DUR.

---

## TASK-009 — Logout All

Implement:

```http
POST /api/v1/auth/logout-all
```

Kullanıcının bütün session'larını revoke et.

Test:

- multiple sessions
- all sessions revoked
- current token invalidation
- refresh tokens invalidation

Sonra DUR.

---

## TASK-010 — MFA Verification

Implement:

```http
POST /api/v1/auth/mfa/verify
```

TOTP authentication.

Requirements:

- temporary login token
- TOTP validation
- one-time semantics
- backup code support
- AUTH_005

Test:

- valid code
- invalid code
- expired temporary token
- reused temporary token
- backup code
- reused backup code

Sonra DUR.

---

## TASK-011 — Profile Update

Implement:

```http
PATCH /api/v1/auth/me
```

Kullanıcı yalnızca kendi profilini güncelleyebilir.

Admin/user management yapma.

Test:

- valid update
- invalid fields
- unauthorized
- forbidden fields
- email uniqueness

Sonra DUR.

---

## TASK-012 — Change Password

Implement:

```http
POST /api/v1/auth/change-password
```

Requirements:

- current password
- new password
- Argon2id
- password history
- session invalidation policy

Mimarinin mevcut kurallarına uy.

Sonra DUR.

---

## TASK-013 — Forgot Password

Implement:

```http
POST /api/v1/auth/forgot-password
```

Requirements:

- email enumeration protection
- secure random reset token
- hashed token storage
- 15 minute expiration
- generic response

Gerçek email provider yoksa abstraction/mock kullan.

Sonra DUR.

---

## TASK-014 — Reset Password

Implement:

```http
POST /api/v1/auth/reset-password
```

Requirements:

- reset token verification
- expiration
- one-time usage
- password validation
- password history
- session invalidation

Test:

- valid
- expired
- reused
- malformed
- weak password

Sonra DUR.

---

## TASK-015 — Session Management

Implement:

```http
GET /api/v1/auth/sessions
```

ve:

```http
DELETE /api/v1/auth/sessions/{id}
```

Kullanıcı sadece kendi session'larını görebilir / revoke edebilir.

Session response içinde:

```text
id
device
ip
user_agent
created_at
last_used_at
expires_at
current
```

gibi güvenli alanlar döndürülebilir.

Refresh token veya hash'i response'a ASLA koyma.

Sonra DUR.

---

## TASK-016 — Auth Error Standardization

Authentication endpointlerinin tamamını ortak error envelope'a geçir.

Kontrol et:

```text
AUTH_001
AUTH_002
AUTH_004
AUTH_005
AUTH_006
VAL_001
RATE_001
```

User enumeration korunmalı.

Sonra DUR.

---

## TASK-017 — Comprehensive Auth Test Matrix

Tüm auth endpointlerini test et.

Minimum:

```text
Login
MFA
Refresh
Logout
Logout All
Me
Profile Update
Change Password
Forgot Password
Reset Password
Sessions
Session Revocation
```

Her endpoint için:

- success
- validation error
- authentication error
- authorization error
- edge cases
- security cases

test et.

Özellikle:

```text
refresh token replay
access token blacklist
account lock
user enumeration
password reuse
session revocation
```

kontrol et.

Sonra DUR.

---

# HER TASK SONUNDA RAPOR FORMATI

Her task tamamlandığında yalnızca şu formatta raporla:

```text
TASK: TASK-XXX
STATUS: COMPLETED / BLOCKED / FAILED

CHANGED:
- file
- file

IMPLEMENTED:
- ...
- ...

TESTS:
- ...
- ...

SECURITY CHECK:
- ...

ACCEPTANCE CRITERIA:
- [x] ...
- [x] ...

NOTES:
- ...

NEXT:
TASK-XXX
```

Ama `NEXT` task'ını otomatik başlatma.

Kullanıcı onayı bekle.

---

# KESİN KURALLAR

1. Kullanıcı onayı olmadan sonraki task'a geçme.

2. Mevcut çalışan kodu gereksiz yere refactor etme.

3. Authentication dışındaki modüllere dokunma.

4. Router içinde business logic yazma.

5. Password plaintext saklama.

6. Refresh token plaintext database'de saklama.

7. Token veya password'u loglama.

8. Secret'ları source code içine yazma.

9. JWT signature verification atlama.

10. JWT issuer/audience kontrolünü atlama.

11. Refresh token rotation'ı atlama.

12. User enumeration açığı oluşturma.

13. MFA secret veya backup code'ları plaintext saklama.

14. Testleri yazmadan task'ı tamamlandı olarak kabul etme.

15. Var olmayan infrastructure'ı varsayma.

16. Bir dependency eksikse önce mevcut projeyi incele.

17. Mimari dokümanda olmayan bir davranış gerekiyorsa bunu açıkça belirt ve kullanıcı onayı olmadan mimari kararı değiştirme.

18. Güvenlik açısından daha doğru olduğunu düşündüğün bir değişiklik varsa doğrudan uygulamak yerine raporda belirt.

19. "Daha temiz olur" gerekçesiyle tüm projeyi yeniden yapılandırma.

20. Her task minimum ve kontrollü değişiklik prensibiyle ilerlemeli.

---

# BAŞLANGIÇ

Şimdi yalnızca:

## TASK-001 — Repository & Architecture Audit

ile başla.

Önce repository'yi incele.

Kod değiştirme.

Analysis sonucunu raporla.

Ve DUR.