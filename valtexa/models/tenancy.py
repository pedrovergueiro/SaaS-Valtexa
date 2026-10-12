"""Clientes, usuários e papéis.

Um usuário existe uma vez na plataforma e pertence a *N* tenants por
:class:`Membership` — o agrônomo de cooperativa atende várias fazendas com uma
conta só, e o papel dele pode ser diferente em cada uma.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valtexa.models.base import Base, Timestamped, UUIDPrimaryKey, enum_column
from valtexa.models.enums import PlatformRole, Role, SupportMode


class Tenant(UUIDPrimaryKey, Timestamped, Base):
    """Uma organização cliente: produtor, cooperativa ou revenda."""

    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(160), nullable=False, doc="Nome ou razão social.")
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    document: Mapped[str | None] = mapped_column(String(32), doc="CNPJ ou CPF.")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- contato e endereço ---------------------------------------------------
    # Tudo opcional de propósito: o cadastro precisa poder ser salvo no meio de
    # uma ligação, com o que já se sabe. Exigir endereço completo para criar um
    # cliente faria a pessoa inventar um — e um endereço inventado é pior do que
    # um campo vazio, porque parece preenchido.
    contact_name: Mapped[str | None] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(255), doc="Logradouro, número e bairro.")
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(2), doc="Sigla da unidade federativa.")
    postal_code: Mapped[str | None] = mapped_column(String(16))
    contracted_service: Mapped[str | None] = mapped_column(
        String(120),
        doc=(
            "Tipo de operação contratada, em texto livre: 'monitoramento com "
            "rover', 'monitoramento + coleta aérea'. Texto e não enumeração "
            "porque o catálogo comercial ainda está mudando, e uma enumeração "
            "errada obrigaria migração a cada contrato novo."
        ),
    )
    notes: Mapped[str | None] = mapped_column(String(1000))

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
    platform_role: Mapped[PlatformRole | None] = mapped_column(
        enum_column(PlatformRole),
        index=True,
        doc=(
            "Papel na equipe da ValTexa (seção 28 do brief). Nulo para quem é só "
            "cliente. Substitui a antiga marca única ``is_platform_admin``: a migração "
            "0010 levou quem a tinha para ``superadmin``."
        ),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @hybrid_property
    def is_platform_admin(self) -> bool:
        """Se a pessoa é da equipe da ValTexa, com qualquer papel de plataforma.

        Mantido para compatibilidade: o contrato HTTP (``/auth/me``) e o console
        ainda leem este nome. **Não** concede nada por si — o que cada papel
        pode está em :data:`valtexa.security.rbac.PLATFORM_ROLE_CAPABILITIES`.
        """
        return self.platform_role is not None

    @is_platform_admin.inplace.setter
    def _is_platform_admin_setter(self, value: bool) -> None:
        # Ligar a marca antiga equivale ao papel que ela tinha (tudo); desligar
        # tira qualquer papel de plataforma. Um papel já mais restrito não é
        # promovido por acidente ao se gravar ``True`` de novo.
        if value and self.platform_role is None:
            self.platform_role = PlatformRole.SUPERADMIN
        elif not value:
            self.platform_role = None

    @is_platform_admin.inplace.expression
    @classmethod
    def _is_platform_admin_expression(cls):
        return cls.platform_role.is_not(None)


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


class UserSession(UUIDPrimaryKey, Timestamped, Base):
    """Uma sessão aberta: o que torna um token revogável.

    Sem esta tabela, o token de sessão é um papel assinado: vale enquanto não
    vence, e nada no servidor pode desdizê-lo. Doze horas é pouco para um
    invasor e muito para um notebook roubado — e a diferença entre os dois é
    exatamente a decisão que alguém precisa poder tomar às pressas.

    O token carrega o ``sid`` desta linha. Toda requisição autenticada confere
    a linha, o que custa uma consulta por chamada — o preço de poder dizer
    "esta sessão acabou agora" em vez de "acaba em algumas horas".

    A linha **não** guarda o token. Guarda o suficiente para a pessoa se
    reconhecer na lista ("Chrome no Windows, ontem à noite") e decidir o que
    derrubar. Um token guardado aqui seria uma segunda cópia da credencial,
    esperando vazamento.
    """

    __tablename__ = "user_session"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("tenant.id", ondelete="SET NULL"),
        index=True,
        doc="O cliente escolhido no login. Nulo para quem entrou sem escolher.",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc=(
            "Atualizado com granularidade grossa, não a cada requisição: uma "
            "escrita por chamada transformaria toda leitura numa escrita, e o "
            "que a pessoa precisa saber é 'hoje de manhã', não 'há 3 segundos'."
        ),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_by: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("user.id", ondelete="SET NULL"),
        doc="Quem derrubou. Nulo quando foi a própria pessoa saindo.",
    )
    revoked_reason: Mapped[str | None] = mapped_column(String(200))
    user_agent: Mapped[str | None] = mapped_column(
        String(300), doc="Como o navegador se apresentou, para a pessoa se reconhecer na lista."
    )
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(foreign_keys=[user_id])

    @property
    def is_active(self) -> bool:
        """Viva: não revogada e ainda dentro da validade."""
        if self.revoked_at is not None:
            return False
        expira = self.expires_at
        if expira is not None and expira.tzinfo is None:
            expira = expira.replace(tzinfo=UTC)
        return expira is None or expira > datetime.now(UTC)


class SupportSession(UUIDPrimaryKey, Timestamped, Base):
    """"Entrar como cliente": a equipe da ValTexa dentro de um cliente, às claras.

    Brief, seção 29: nunca acesso silencioso. Cada entrada tem quem, em qual
    cliente, por quê, até quando e em que modo; cada requisição feita com ela
    fica na auditoria do cliente com o nome do interno; a saída também.

    O token emitido para a sessão carrega ``sup=<id desta linha>`` e aponta para
    uma :class:`UserSession` própria (``user_session_id``), com validade igual ao
    prazo. Encerrar a sessão de suporte derruba essa sessão — o token deixa de
    valer na hora, sem esperar vencer.
    """

    __tablename__ = "support_session"

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True,
        doc="O interno da ValTexa que entrou.",
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True,
        doc="O cliente em que entrou.",
    )
    user_session_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("user_session.id", ondelete="SET NULL"),
        doc="A sessão de login criada para este acesso; cai junto com ele.",
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, doc="Motivo declarado. Obrigatório.")
    ticket_ref: Mapped[str | None] = mapped_column(
        String(80), doc="Chamado ou referência externa, quando houver."
    )
    ticket_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("support_ticket.id", ondelete="SET NULL"), index=True,
        doc="O chamado (do mesmo cliente) que motivou a entrada, quando há (Parte 6).",
    )
    mode: Mapped[SupportMode] = mapped_column(
        enum_column(SupportMode), nullable=False, default=SupportMode.LEITURA
    )
    assisted_reason: Mapped[str | None] = mapped_column(
        Text, doc="Por que a escrita foi ligada. Exigido para o modo assistido."
    )
    assisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ended_reason: Mapped[str | None] = mapped_column(
        String(200), doc="'saiu', 'expirou', 'encerrada por ...'."
    )
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, doc="Quantas requisições foram feitas com ela."
    )

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    tenant: Mapped[Tenant] = relationship(foreign_keys=[tenant_id])

    @property
    def is_open(self) -> bool:
        """Aberta: não encerrada e dentro do prazo."""
        if self.ended_at is not None:
            return False
        expira = self.expires_at
        if expira is not None and expira.tzinfo is None:
            expira = expira.replace(tzinfo=UTC)
        return expira > datetime.now(UTC)
