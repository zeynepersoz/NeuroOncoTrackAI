"""
Klinisyen / Doktor (PHYSICIAN) hesabı oluşturma / güncelleme betiği.

Kullanım örneği:
    python create_doctor.py --email dr.ahmet@hastane.edu.tr --password "StrongPass!123" --first-name Ahmet --last-name Yılmaz --title "Uzm. Dr." --org-name "Ankara Şehir Hastanesi" --org-code "NOT-2026"

Ortam değişkenleri ile:
    DOCTOR_EMAIL=dr.ahmet@hastane.edu.tr
    DOCTOR_PASSWORD="StrongPass!123"
    DOCTOR_FIRST_NAME="Ahmet"
    DOCTOR_LAST_NAME="Yılmaz"
    DOCTOR_TITLE="Uzm. Dr. Radyolog"
    DOCTOR_ORG_NAME="Ankara Şehir Hastanesi"
    DOCTOR_ORG_CODE="NOT-2026"
    python create_doctor.py
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
            "Örnek: doktor@hastane.edu.tr veya dr.ahmet@example.com"
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
    final_name = org_name.strip() if org_name and org_name.strip() else "Ankara Şehir Hastanesi"
    final_code = org_code.strip().upper() if org_code and org_code.strip() else "NOT-2026"

    # Kod belirtilmişse önce koda göre ara
    if org_code and org_code.strip():
        stmt = select(Organization).where(func.lower(Organization.code) == final_code.lower())
        result = await db.execute(stmt)
        existing = result.scalars().first()
        if existing:
            return existing

    # İsme göre var olan kurumu ara
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


async def create_doctor(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    title: str,
    org_name: str,
    org_code: str | None,
) -> dict[str, str]:
    """Doktor / Klinisyen (PHYSICIAN) hesabı oluşturur veya günceller."""

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
            # Yeni doktor hesabı oluştur
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email=normalized_email,
                password_hash=hash_password(password),
                first_name=first_name.strip() or "Ahmet",
                last_name=last_name.strip() or "Yılmaz",
                title=title.strip() if title else "Uzm. Dr.",
                role=Role.PHYSICIAN.value,
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
            # Mevcut kullanıcıyı PHYSICIAN rolüne ata ve güncelle
            user.organization_id = org.id
            user.email = normalized_email
            user.first_name = first_name.strip() or user.first_name
            user.last_name = last_name.strip() or user.last_name
            user.title = title.strip() if title else (user.title or "Uzm. Dr.")
            user.role = Role.PHYSICIAN.value
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
            "title": user.title,
            "full_name": f"{user.first_name} {user.last_name}",
            "organization_id": str(user.organization_id),
            "organization_name": org.name,
            "organization_code": org.code,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Doktor / Klinisyen (PHYSICIAN) hesabı oluştur veya güncelle."
    )

    parser.add_argument(
        "--email",
        default=os.getenv("DOCTOR_EMAIL"),
        help="Doktor e-posta adresi (Örn: dr.ahmet@hastane.edu.tr veya dr.ahmet@example.com)",
    )

    parser.add_argument(
        "--password",
        default=os.getenv("DOCTOR_PASSWORD"),
        help="Güçlü parola (en az 12 karakter, büyük/küçük harf, rakam, özel karakter)",
    )

    parser.add_argument(
        "--first-name",
        default=os.getenv("DOCTOR_FIRST_NAME", "Ahmet"),
        help="Ad",
    )

    parser.add_argument(
        "--last-name",
        default=os.getenv("DOCTOR_LAST_NAME", "Yılmaz"),
        help="Soyad",
    )

    parser.add_argument(
        "--title",
        default=os.getenv("DOCTOR_TITLE", "Uzm. Dr."),
        help="Unvan (Örn: Uzm. Dr., Prof. Dr., Doç. Dr., Nöroradyolog)",
    )

    parser.add_argument(
        "--org-name",
        default=os.getenv("DOCTOR_ORG_NAME", "Ankara Şehir Hastanesi"),
        help="Bağlı olduğu kurum/hastane adı",
    )

    parser.add_argument(
        "--org-code",
        default=os.getenv("DOCTOR_ORG_CODE", "NOT-2026"),
        help="Kurum kodu (Örn: NOT-2026)",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if not args.email:
        raise SystemExit(
            "--email veya DOCTOR_EMAIL tanımlanmalıdır.\n"
            "Örnek: python create_doctor.py --email dr.ahmet@example.com --password \"StrongPass!123\""
        )

    if not args.password:
        raise SystemExit(
            "--password veya DOCTOR_PASSWORD tanımlanmalıdır."
        )

    try:
        result = await create_doctor(
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
            f"Doktor hesabı oluşturulamadı: {exc}"
        ) from exc

    print()
    print("=" * 60)
    print("DOKTOR / KLİNİSYEN (PHYSICIAN) HESABI HAZIRLANDI")
    print("=" * 60)

    print(f"İşlem          : {result['action']}")
    print(f"Doktor         : {result['title']} {result['full_name']}")
    print(f"E-posta        : {result['email']}")
    print(f"Sistem Rolü    : {result['role']} (Klinisyen / Doktor)")
    print(
        f"Bağlı Kurum    : "
        f"{result['organization_name']} "
        f"({result['organization_code']})"
    )
    print(f"Kurum ID       : {result['organization_id']}")

    print()
    print("Kullanılacak Giriş Parolası:")
    print(args.password)
    print()


if __name__ == "__main__":
    asyncio.run(main())
