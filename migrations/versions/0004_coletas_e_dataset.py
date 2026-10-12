"""Coletas, fila de processamento e dataset proprietário.

Revisão: 0004
Anterior: 0003

Sete tabelas e uma ampliação de coluna.

``collection`` e ``collection_file`` são o lote de arquivos que entra pelo painel
administrativo — o caminho do MVP, em que o voo é de um operador terceirizado e
a ingestão é manual. ``processing_job`` é o que permite ao administrador fechar
a aba: o trabalho pesado sai da requisição e vai para o worker.

``dataset``, ``dataset_sample``, ``dataset_version`` e ``model_version`` guardam
o ativo que a operação produz: a anotação do agrônomo, o corte congelado que vai
para o treino e a versão de modelo que saiu dele.

A ampliação de ``subject_type`` de ``VARCHAR(12)`` não é cosmética: os assuntos
novos ``collection_file`` e ``dataset_version`` têm 15 caracteres, e sem isto a
primeira entrada de auditoria de uma coleta seria truncada no Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("crop", sa.String(length=64), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("ground", "aerial", "any", name="captureplatform", native_enum=False),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("dataset", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_dataset_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_dataset_key"), ["key"], unique=True)

    op.create_table(
        "dataset_version",
        sa.Column("dataset_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("label_counts", sa.JSON(), nullable=False),
        sa.Column("sample_ids", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_by", sa.String(length=32), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["frozen_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
    )
    with op.batch_alter_table("dataset_version", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_dataset_version_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_dataset_version_dataset_id"), ["dataset_id"], unique=False
        )

    op.create_table(
        "processing_job",
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress_done", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("processing_job", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_processing_job_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_processing_job_kind"), ["kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_processing_job_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_processing_job_subject_id"), ["subject_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_processing_job_tenant_id"), ["tenant_id"], unique=False
        )

    op.create_table(
        "model_version",
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "registered",
                "training",
                "trained",
                "shadow",
                "production",
                "retired",
                name="modelversionstate",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.Enum("ground", "aerial", "any", name="captureplatform", native_enum=False),
            nullable=False,
        ),
        sa.Column("crop", sa.String(length=64), nullable=True),
        sa.Column("dataset_version_id", sa.String(length=32), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_version.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_key", "version", name="uq_model_version"),
    )
    with op.batch_alter_table("model_version", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_model_version_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_model_version_dataset_version_id"), ["dataset_version_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_model_version_model_key"), ["model_key"], unique=False)
        batch_op.create_index(batch_op.f("ix_model_version_state"), ["state"], unique=False)

    op.create_table(
        "collection",
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("farm_id", sa.String(length=32), nullable=False),
        sa.Column("field_id", sa.String(length=32), nullable=False),
        sa.Column("collected_on", sa.Date(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "drone_third_party",
                "rover",
                "handheld",
                "drone_owned",
                name="collectionsource",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "aerial_image",
                "orthomosaic",
                "ground_image",
                "other",
                name="collectionkind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "platform",
            sa.Enum("ground", "aerial", "any", name="captureplatform", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                "draft",
                "uploading",
                "upload_completed",
                "processing_queued",
                "ai_processing",
                "results_generated",
                "review_required",
                "analyzed",
                "available_to_client",
                "failed",
                "cancelled",
                name="collectionstate",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("operator_name", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("bytes_total", sa.BigInteger(), nullable=False),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False),
        sa.Column("files_stored", sa.Integer(), nullable=False),
        sa.Column("files_processed", sa.Integer(), nullable=False),
        sa.Column("files_analyzed", sa.Integer(), nullable=False),
        sa.Column("files_needs_review", sa.Integer(), nullable=False),
        sa.Column("files_no_model", sa.Integer(), nullable=False),
        sa.Column("files_failed", sa.Integer(), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=True),
        sa.Column("no_model_reason", sa.Text(), nullable=True),
        sa.Column("upload_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("released_by", sa.String(length=32), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["farm_id"], ["farm.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["released_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_collection_code"), ["code"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_created_by"), ["created_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_farm_id"), ["farm_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_field_id"), ["field_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_state"), ["state"], unique=False)
        batch_op.create_index(batch_op.f("ix_collection_tenant_id"), ["tenant_id"], unique=False)

    op.create_table(
        "collection_file",
        sa.Column("collection_id", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_declared", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("received_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "registered",
                "uploading",
                "stored",
                "processing",
                "analyzed",
                "needs_review",
                "no_model",
                "failed",
                "rejected",
                name="collectionfilestate",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("alt_m", sa.Float(), nullable=True),
        sa.Column("asset_id", sa.String(length=32), nullable=True),
        sa.Column("observation_id", sa.String(length=32), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["observation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("collection_file", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_collection_file_asset_id"), ["asset_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_collection_file_collection_id"), ["collection_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_collection_file_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_collection_file_observation_id"), ["observation_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_collection_file_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_collection_file_tenant_id"), ["tenant_id"], unique=False
        )

    op.create_table(
        "dataset_sample",
        sa.Column("dataset_id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("asset_id", sa.String(length=32), nullable=False),
        sa.Column("observation_id", sa.String(length=32), nullable=True),
        sa.Column("diagnosis_id", sa.String(length=32), nullable=True),
        sa.Column("collection_id", sa.String(length=32), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("machine_label", sa.String(length=120), nullable=True),
        sa.Column("machine_confidence", sa.Float(), nullable=True),
        sa.Column("disagreed", sa.Boolean(), nullable=False),
        sa.Column("reviewer_id", sa.String(length=32), nullable=True),
        sa.Column("reviewer_label", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "candidate", "included", "excluded", name="datasetsamplestate", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["diagnosis_id"], ["diagnosis.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["observation_id"], ["observation.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "diagnosis_id", name="uq_dataset_sample_diagnosis"),
    )
    with op.batch_alter_table("dataset_sample", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_dataset_sample_asset_id"), ["asset_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_collection_id"), ["collection_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_dataset_id"), ["dataset_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_diagnosis_id"), ["diagnosis_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_disagreed"), ["disagreed"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_dataset_sample_label"), ["label"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_reviewer_id"), ["reviewer_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_dataset_sample_state"), ["state"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_dataset_sample_tenant_id"), ["tenant_id"], unique=False
        )

    # A observação deixa de exigir dispositivo. No MVP a imagem aérea vem de um
    # operador terceirizado: inventar um Device para ela registraria no banco um
    # voo da ValTexa que não aconteceu. Quem responde pela origem é collection_id.
    with op.batch_alter_table("observation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_id", sa.String(length=32), nullable=True))
        batch_op.alter_column("device_id", existing_type=sa.VARCHAR(length=32), nullable=True)
        batch_op.create_index(
            batch_op.f("ix_observation_collection_id"), ["collection_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_observation_collection",
            "collection",
            ["collection_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("audit_entry", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.VARCHAR(length=12),
            type_=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            existing_nullable=False,
        )

    with op.batch_alter_table("outbox_event", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.VARCHAR(length=12),
            type_=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            existing_nullable=True,
        )

    with op.batch_alter_table("safety_evaluation", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.VARCHAR(length=12),
            type_=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("safety_evaluation", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            type_=sa.VARCHAR(length=12),
            existing_nullable=False,
        )

    with op.batch_alter_table("outbox_event", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            type_=sa.VARCHAR(length=12),
            existing_nullable=True,
        )

    with op.batch_alter_table("audit_entry", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_type",
            existing_type=sa.Enum(
                "mission",
                "application",
                "device",
                "diagnosis",
                "decision",
                "observation",
                "product",
                "tank",
                "user",
                "field",
                "verification",
                "collection",
                "collection_file",
                "dataset",
                "dataset_version",
                "model_version",
                "tenant",
                name="subjecttype",
                native_enum=False,
            ),
            type_=sa.VARCHAR(length=12),
            existing_nullable=False,
        )

    with op.batch_alter_table("observation", schema=None) as batch_op:
        batch_op.drop_constraint("fk_observation_collection", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_observation_collection_id"))
        batch_op.alter_column("device_id", existing_type=sa.VARCHAR(length=32), nullable=False)
        batch_op.drop_column("collection_id")

    with op.batch_alter_table("dataset_sample", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dataset_sample_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_state"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_reviewer_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_label"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_disagreed"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_diagnosis_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_created_at"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_collection_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_sample_asset_id"))

    op.drop_table("dataset_sample")
    with op.batch_alter_table("collection_file", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collection_file_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_collection_file_state"))
        batch_op.drop_index(batch_op.f("ix_collection_file_observation_id"))
        batch_op.drop_index(batch_op.f("ix_collection_file_created_at"))
        batch_op.drop_index(batch_op.f("ix_collection_file_collection_id"))
        batch_op.drop_index(batch_op.f("ix_collection_file_asset_id"))

    op.drop_table("collection_file")
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_collection_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_collection_state"))
        batch_op.drop_index(batch_op.f("ix_collection_field_id"))
        batch_op.drop_index(batch_op.f("ix_collection_farm_id"))
        batch_op.drop_index(batch_op.f("ix_collection_created_by"))
        batch_op.drop_index(batch_op.f("ix_collection_created_at"))
        batch_op.drop_index(batch_op.f("ix_collection_code"))

    op.drop_table("collection")
    with op.batch_alter_table("model_version", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_model_version_state"))
        batch_op.drop_index(batch_op.f("ix_model_version_model_key"))
        batch_op.drop_index(batch_op.f("ix_model_version_dataset_version_id"))
        batch_op.drop_index(batch_op.f("ix_model_version_created_at"))

    op.drop_table("model_version")
    with op.batch_alter_table("processing_job", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_processing_job_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_processing_job_subject_id"))
        batch_op.drop_index(batch_op.f("ix_processing_job_state"))
        batch_op.drop_index(batch_op.f("ix_processing_job_kind"))
        batch_op.drop_index(batch_op.f("ix_processing_job_created_at"))

    op.drop_table("processing_job")
    with op.batch_alter_table("dataset_version", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dataset_version_dataset_id"))
        batch_op.drop_index(batch_op.f("ix_dataset_version_created_at"))

    op.drop_table("dataset_version")
    with op.batch_alter_table("dataset", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_dataset_key"))
        batch_op.drop_index(batch_op.f("ix_dataset_created_at"))

    op.drop_table("dataset")
