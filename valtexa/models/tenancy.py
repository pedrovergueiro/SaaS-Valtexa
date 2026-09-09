"""Clientes, usuários e papéis.

Um usuário existe uma vez na plataforma e pertence a *N* tenants por
:class:`Membership` — o agrônomo de cooperativa atende várias fazendas com uma
conta só, e o papel dele pode ser diferente em cada uma.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import Role


class Tenant(UUIDPrimaryKey, Timestamped, Base):
    """Uma organização cliente: produtor, cooperativa ou revenda."""

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    document: Mapped[str | None] = mapped_column(String(32), doc="CNPJ ou CPF.")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class User(UUIDPrimaryKey, Timestamped, Base):
    """Uma pessoa. O ``password_hash`` guarda scrypt; ver ``security/passwords.py``."""

    __tablename__ = "user"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Equipe da ValTexa. Enxerga todos os tenants; toda ação fica na auditoria.",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Membership(UUIDPrimaryKey, Timestamped, Base):
    """O papel de um usuário dentro de um tenant."""

    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(enum_column(Role), nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
