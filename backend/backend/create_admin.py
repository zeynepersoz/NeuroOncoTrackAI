"""
Normal hastane yöneticisi (HOSPITAL_ADMIN) oluşturma / güncelleme betiği.

Kullanım örneği:
    python create_admin.py --email hastane_admin@example.com --password "StrongPass!123" --first-name Ahmet --last-name Yılmaz --org-name "Ankara Şehir Hastanesi" --org-code "ORG_ANKARA"

Ortam değişkenleri ile:
    ADMIN_EMAIL=hastane_admin@example.com
    ADMIN_PASSWORD="StrongPass!123"
    ADMIN_FIRST_NAME="Ahmet"
    ADMIN_LAST_NAME="Yılmaz"
    ADMIN_ORG_NAME="Ankara Şehir Hastanesi"
    ADMIN_ORG_CODE="ORG_ANKARA"
    python create_admin.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.permissions import Role
from app.core.security import hash_password, validate_password
from app.db.session import async_session_factory
from app.models.organization import Organization
from app.models.user import User


def validate_email(email: str) -> str:
    """E-posta adresini normalize eder ve temel format kontrolü yapar."""
    normalized = email.strip().lower()

    if not normalized:
        raise ValueError("E-posta boş olamaz.")

    email_pattern = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"

    if not re.match(email_pattern, normalized):
        raise ValueError(
            f"Geçersiz e-posta adresi: {normalized}. "
            "Örnek: admin@hastane.edu.tr veya admin@example.com"
        )

    domain = normalized.rsplit("@", 1)[1]

    reserved_domains = {
        "local",
        "localhost",
        "test",
        "invalid",
        "example",
        "example.com",
        "example.net",
        "example.org",
    }

    if domain in reserved_domains and domain != "example.com":
        raise ValueError(
            f"'{domain}' özel/reserved bir domain olduğu için e-posta adresi olarak kullanılamaz."
        )

    return normalized


async def ensure_organization(
    db,
    org_name: str,
    org_code: str | None,
) -> Organization:
    """Kurum varsa bulur, yoksa otomatik oluşturur."""
    final_name = org_name.strip() if org_name and org_name.strip() else "Merkez Hastane"
    final_code = org_code.strip().upper() if org_code and org_code.strip() else f"ORG_{uuid.uuid4().hex[:6].upper()}"

    # Kod belirtilmişse önce koda göre ara, yoksa isme göre ilkini bul
    if org_code and org_code.strip():
        stmt = select(Organization).where(func.lower(Organization.code) == final_code.lower())
        result = await db.execute(stmt)
        existing = result.scalars().first()
        if existing:
            return existing

    # İsme göre var olan kurumu ara (birden fazla varsa ilkini al)
    stmt = select(Organization).where(func.lower(Organization.name) == final_name.lower())
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        return existing

    org = Organization(
        id=uuid.uuid4(),
        name=final_name,
        code=final_code,
        org_type="UNIVERSITY_HOSPITAL",
        is_active=True,
        description="Otomatik oluşturulan hastane/kurum.",
    )

    db.add(org)
    await db.flush()

    return org


async def create_admin(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    title: str,
    org_name: str,
    org_code: str | None,
) -> dict[str, str]:
    """Hastane yöneticisi (HOSPITAL_ADMIN) hesabı oluşturur veya günceller."""

    normalized_email = validate_email(email)
    validate_password(password)

    async with async_session_factory() as db:
        org = await ensure_organization(
            db=db,
            org_name=org_name,
            org_code=org_code,
        )

        stmt = select(User).where(func.lower(User.email) == normalized_email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if user is None:
            # Yeni hastane yöneticisi oluştur
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email=normalized_email,
                password_hash=hash_password(password),
                first_name=first_name.strip() or "Hastane",
                last_name=last_name.strip() or "Yöneticisi",
                title=title.strip() if title else "Hastane Müdürü",
                role=Role.HOSPITAL_ADMIN.value,
                extra_permissions=[],
                revoked_permissions=[],
                is_active=True,
                is_locked=False,
                failed_login_attempts=0,
                mfa_enabled=False,
                must_change_password=False,
                password_changed_at=now,
                created_by=None,
                archived_at=None,
            )

            db.add(user)
            await db.commit()
            await db.refresh(user)
            action = "created"

        else:
            # Mevcut kullanıcıyı HOSPITAL_ADMIN rolüne ata ve güncelle
            user.organization_id = org.id
            user.email = normalized_email
            user.first_name = first_name.strip() or user.first_name
            user.last_name = last_name.strip() or user.last_name
            user.title = title.strip() if title else (user.title or "Hastane Müdürü")
            user.role = Role.HOSPITAL_ADMIN.value
            user.password_hash = hash_password(password)
            user.is_active = True
            user.is_locked = False
            user.locked_until = None
            user.failed_login_attempts = 0
            user.must_change_password = False
            user.password_changed_at = now
            user.extra_permissions = []
            user.revoked_permissions = []

            await db.commit()
            action = "updated"

        return {
            "action": action,
            "email": user.email,
            "role": user.role,
            "organization_id": str(user.organization_id),
            "organization_name": org.name,
            "organization_code": org.code,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hastane Yöneticisi (HOSPITAL_ADMIN) hesabı oluştur."
    )

    parser.add_argument(
        "--email",
        default=os.getenv("ADMIN_EMAIL"),
        help="Yönetici e-posta adresi",
    )

    parser.add_argument(
        "--password",
        default=os.getenv("ADMIN_PASSWORD"),
        help="Güçlü bir parola",
    )

    parser.add_argument(
        "--first-name",
        default=os.getenv("ADMIN_FIRST_NAME", "Hastane"),
        help="Ad",
    )

    parser.add_argument(
        "--last-name",
        default=os.getenv("ADMIN_LAST_NAME", "Yöneticisi"),
        help="Soyad",
    )

    parser.add_argument(
        "--title",
        default=os.getenv("ADMIN_TITLE", "Hastane Müdürü"),
        help="Unvan (Örn: Doç. Dr., Başhekim, Hastane Müdürü)",
    )

    parser.add_argument(
        "--org-name",
        default=os.getenv("ADMIN_ORG_NAME", "Ankara Şehir Hastanesi"),
        help="Bağlı olduğu kurum/hastane adı",
    )

    parser.add_argument(
        "--org-code",
        default=os.getenv("ADMIN_ORG_CODE", None),
        help="Kurum kodu (Varsayılan: otomatik veya var olan)",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if not args.email:
        raise SystemExit(
            "--email veya ADMIN_EMAIL tanımlanmalıdır. Örnek: python create_admin.py --email admin@hastane.edu.tr --password StrongPassword123!"
        )

    if not args.password:
        raise SystemExit(
            "--password veya ADMIN_PASSWORD tanımlanmalıdır."
        )

    try:
        result = await create_admin(
            email=args.email,
            password=args.password,
            first_name=args.first_name,
            last_name=args.last_name,
            title=args.title,
            org_name=args.org_name,
            org_code=args.org_code,
        )

    except Exception as exc:
        raise SystemExit(
            f"Hesap oluşturulamadı: {exc}"
        ) from exc

    print()
    print("=" * 55)
    print("HASTANE YÖNETİCİSİ (HOSPITAL_ADMIN) OLUŞTURULDU")
    print("=" * 55)

    print(f"İşlem          : {result['action']}")
    print(f"E-posta        : {result['email']}")
    print(f"Rol            : {result['role']} (Hastane Yöneticisi)")
    print(
        f"Bağlı Kurum    : "
        f"{result['organization_name']} "
        f"({result['organization_code']})"
    )
    print(f"Kurum ID       : {result['organization_id']}")

    print()
    print("Giriş için parola:")
    print(args.password)
    print()


if __name__ == "__main__":
    asyncio.run(main())
