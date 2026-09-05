"""
Tek seferlik süper admin oluşturma betiği.

Kullanım örneği:
    python create_super_admin.py --email admin@example.com --password "StrongPass!123" --first-name Admin --last-name User --org-name "NeuroOncoTrack"

Ortam değişkenleri ile:
    SUPER_ADMIN_EMAIL=admin@example.com
    SUPER_ADMIN_PASSWORD="StrongPass!123"
    python create_super_admin.py
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
    """
    E-posta adresini normalize eder ve temel format kontrolü yapar.

    .local gibi özel/reserved domain'leri kabul etmez.
    """
    normalized = email.strip().lower()

    if not normalized:
        raise ValueError("E-posta boş olamaz.")

    # Basit ve güvenli e-posta format kontrolü
    email_pattern = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"

    if not re.match(email_pattern, normalized):
        raise ValueError(
            f"Geçersiz e-posta adresi: {normalized}. "
            "Örnek: admin@example.com"
        )

    # Özel/reserved domain'leri engelle
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

    if domain in reserved_domains:
        # example.com'u test amacıyla kullanabilmek için burada
        # özellikle izin verebiliriz.
        if domain == "example.com":
            return normalized

        raise ValueError(
            f"'{domain}' özel/reserved bir domain olduğu için "
            "e-posta adresi olarak kullanılamaz."
        )

    return normalized


async def ensure_organization(
    db,
    org_name: str,
    org_code: str | None,
) -> Organization:
    """Kurum varsa döner, yoksa oluşturur."""

    final_name = (
        org_name.strip()
        if org_name and org_name.strip()
        else "NeuroOncoTrack"
    )

    final_code = (
        org_code.strip().upper()
        if org_code and org_code.strip()
        else "ROOT"
    )

    stmt = select(Organization).where(
        func.lower(Organization.code) == final_code.lower()
    )

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    org = Organization(
        id=uuid.uuid4(),
        name=final_name,
        code=final_code,
        org_type="Health System",
        is_active=True,
        description="Otomatik oluşturulan kök kurum / super admin için.",
    )

    db.add(org)
    await db.flush()

    return org


async def create_super_admin(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    org_name: str,
    org_code: str | None,
) -> dict[str, str]:
    """Tek seferlik süper admin hesabı oluşturur."""

    # E-posta normalize + validate
    normalized_email = validate_email(email)

    # Şifre kontrolü
    validate_password(password)

    async with async_session_factory() as db:
        # Kurumu bul veya oluştur
        org = await ensure_organization(
            db=db,
            org_name=org_name,
            org_code=org_code,
        )

        # Kullanıcıyı e-posta ile bul
        stmt = select(User).where(
            func.lower(User.email) == normalized_email
        )

        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if user is None:
            # Yeni super admin
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email=normalized_email,
                password_hash=hash_password(password),
                first_name=first_name.strip() or "Super",
                last_name=last_name.strip() or "Admin",
                title="System Administrator",
                role=Role.SUPER_ADMIN.value,
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
            # Mevcut kullanıcıyı super admin yap
            user.organization_id = org.id
            user.email = normalized_email

            user.first_name = (
                first_name.strip()
                or user.first_name
            )

            user.last_name = (
                last_name.strip()
                or user.last_name
            )

            user.title = "System Administrator"
            user.role = Role.SUPER_ADMIN.value

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
        description="Tek seferlik süper admin hesabı oluştur."
    )

    parser.add_argument(
        "--email",
        default=os.getenv("SUPER_ADMIN_EMAIL"),
        help="Süper admin e-posta adresi",
    )

    parser.add_argument(
        "--password",
        default=os.getenv("SUPER_ADMIN_PASSWORD"),
        help="Güçlü bir parola",
    )

    parser.add_argument(
        "--first-name",
        default=os.getenv("SUPER_ADMIN_FIRST_NAME", "Super"),
        help="Ad",
    )

    parser.add_argument(
        "--last-name",
        default=os.getenv("SUPER_ADMIN_LAST_NAME", "Admin"),
        help="Soyad",
    )

    parser.add_argument(
        "--org-name",
        default=os.getenv(
            "SUPER_ADMIN_ORG_NAME",
            "NeuroOncoTrack",
        ),
        help="Kurum adı",
    )

    parser.add_argument(
        "--org-code",
        default=os.getenv(
            "SUPER_ADMIN_ORG_CODE",
            "ROOT",
        ),
        help="Kurum kodu",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if not args.email:
        raise SystemExit(
            "--email veya SUPER_ADMIN_EMAIL tanımlanmalıdır."
        )

    if not args.password:
        raise SystemExit(
            "--password veya SUPER_ADMIN_PASSWORD tanımlanmalıdır."
        )

    try:
        result = await create_super_admin(
            email=args.email,
            password=args.password,
            first_name=args.first_name,
            last_name=args.last_name,
            org_name=args.org_name,
            org_code=args.org_code,
        )

    except Exception as exc:
        raise SystemExit(
            f"Hesap oluşturulamadı: {exc}"
        ) from exc

    print()
    print("=" * 50)
    print("SÜPER ADMIN HESABI OLUŞTURULDU")
    print("=" * 50)

    print(f"İşlem          : {result['action']}")
    print(f"E-posta        : {result['email']}")
    print(f"Rol            : {result['role']}")
    print(
        f"Kurum          : "
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