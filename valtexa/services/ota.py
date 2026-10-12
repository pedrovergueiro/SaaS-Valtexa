"""Atualização remota (OTA) do Rover — lado da plataforma (brief, seção 24).

Fluxo::

    publicar pacote (.tar) → conferir conteúdo → guardar no object storage
      → destinar a robôs (um a um ou o cliente inteiro) → envelope assinado por robô
      → o robô baixa (com retomada), confere assinatura e hashes, instala lado a
        lado, confere a saúde, troca e confirma — ou volta sozinho à versão anterior
      → cada passo informado aqui (``POST /v1/device/ota/{id}/status``) e auditado

O que a plataforma garante:

* **pacote seguro de abrir**: só arquivos regulares, sem caminho absoluto nem
  ``..``, sem *link*; cada arquivo com o SHA-256 no manifesto;
* **modelo só do registry**: pacote de modelo precisa apontar uma versão do Model
  Registry **em PRODUÇÃO** e conter ``<sha256>.onnx`` cujo hash é o do artefato
  que a versão manda ao robô (o otimizado, se houver; senão o original). Destinar
  a um cliente exige o modelo liberado para ele;
* **assinatura**: o envelope de cada destino (pacote, manifesto, robô, validade)
  é assinado com a chave OTA da plataforma (:func:`valtexa.security.signing.sign_ota`,
  segredo fora do código: ``OTA_SIGNING_SECRET``). O robô confere com a pública
  que recebeu no provisionamento;
* **rastreio**: estado e histórico por robô; ``aplicada``/``revertida``/``falhou``/
  ``recusada``/``cancelada`` são finais.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from valtexa.models import (
    ActorType,
    Device,
    DeviceStatus,
    ModelVersion,
    ModelVersionState,
    OtaDeployment,
    OtaPackage,
    SubjectType,
    User,
)
from valtexa.models.ota import OTA_FINAL, OTA_KINDS, OTA_STATES
from valtexa.security import signing
from valtexa.services import audit, events, model_registry, storage

MAX_PACOTE_BYTES = 512 * 2**20
VALIDADE_ENVELOPE = timedelta(days=30)
OTA_FALHAS = frozenset({"falhou", "revertida", "recusada"})
"""Estados finais que querem dizer "não atualizou": viram evento ``ota.failed``."""

# Estados que o robô pode informar e de onde.
TRANSICOES_DO_ROBO: dict[str, frozenset[str]] = {
    "pendente": frozenset({"baixando", "verificando", "recusada", "falhou"}),
    "baixando": frozenset({"baixando", "verificando", "falhou", "recusada"}),
    "verificando": frozenset({"instalando", "recusada", "falhou"}),
    "instalando": frozenset({"verificando_saude", "revertida", "falhou"}),
    "verificando_saude": frozenset({"aplicada", "revertida", "falhou"}),
    # Depois de aplicada, o robô ainda pode voltar sozinho se o novo não subir
    # no boot seguinte (confirmação A/B): é o único estado final que muda.
    "aplicada": frozenset({"revertida"}),
}


class OtaError(ValueError):
    def __init__(self, mensagem: str, *, status: int = 409) -> None:
        super().__init__(mensagem)
        self.status = status


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def ler_arquivo(dados: bytes) -> list[dict]:
    """Abre o ``.tar`` e devolve ``[{path, sha256, size_bytes}]``. Recusa o que não é seguro."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(dados), mode="r:*")  # noqa: SIM115
    except tarfile.TarError as exc:
        raise OtaError(f"O pacote não é um .tar válido: {exc}", status=422) from exc
    arquivos = []
    with tar:
        for membro in tar.getmembers():
            nome = membro.name
            if membro.isdir():
                continue
            if not membro.isfile():
                raise OtaError(f"{nome}: só arquivos regulares (sem link nem dispositivo).",
                               status=422)
            if nome.startswith("/") or ".." in nome.split("/") or "\\" in nome:
                raise OtaError(f"{nome}: caminho inseguro no pacote.", status=422)
            conteudo = tar.extractfile(membro).read()
            arquivos.append({"path": nome, "sha256": _sha(conteudo), "size_bytes": len(conteudo)})
    if not arquivos:
        raise OtaError("Pacote vazio.", status=422)
    if len({a["path"] for a in arquivos}) != len(arquivos):
        raise OtaError("Pacote com o mesmo caminho repetido.", status=422)
    return sorted(arquivos, key=lambda a: a["path"])


def artefato_do_robo(versao: ModelVersion) -> tuple[str | None, str | None]:
    """``(sha256, tipo)`` do artefato que a versão manda ao robô."""
    if versao.optimized_artifact_sha256:
        return versao.optimized_artifact_sha256, "otimizado"
    if versao.original_artifact_sha256:
        return versao.original_artifact_sha256, "original"
    return None, None


def publicar_pacote(
    session: Session,
    dados: bytes,
    *,
    kind: str,
    version: str,
    actor: User,
    model_version_id: str | None = None,
    notes: str | None = None,
) -> OtaPackage:
    if kind not in OTA_KINDS:
        raise OtaError(f"Tipo de pacote inválido: {kind}. Use: {', '.join(OTA_KINDS)}.",
                       status=422)
    if len(dados) > MAX_PACOTE_BYTES:
        raise OtaError("Pacote acima de 512 MB.", status=413)
    if session.scalar(select(OtaPackage.id).where(OtaPackage.kind == kind,
                                                  OtaPackage.version == version)):
        raise OtaError(f"Já existe pacote {kind} {version}: pacote não se reescreve.")
    arquivos = ler_arquivo(dados)
    modelo: dict | None = None
    versao_modelo: ModelVersion | None = None
    if kind == "model":
        if not model_version_id:
            raise OtaError("Pacote de modelo precisa da versão do registry (model_version_id).",
                           status=422)
        versao_modelo = session.get(ModelVersion, model_version_id)
        if versao_modelo is None:
            raise OtaError("Versão de modelo não encontrada.", status=404)
        if versao_modelo.state is not ModelVersionState.PRODUCAO:
            raise OtaError(
                f"{versao_modelo.model_key} {versao_modelo.version} está em "
                f"{model_registry.ROTULOS[versao_modelo.state]}: só modelo em PRODUÇÃO no "
                "registry vai para o robô."
            )
        sha, tipo = artefato_do_robo(versao_modelo)
        if sha is None:
            raise OtaError("A versão não tem artefato com hash no registry.")
        esperado = f"{sha}.onnx"
        achado = next((a for a in arquivos if a["path"] == esperado), None)
        if achado is None or achado["sha256"] != sha:
            raise OtaError(
                f"O pacote precisa conter {esperado} com exatamente o hash do registry "
                f"(artefato {tipo})."
            )
        modelo = {"model_key": versao_modelo.model_key, "version": versao_modelo.version,
                  "artifact_sha256": sha, "artifact_kind": tipo,
                  "dnaty_version": versao_modelo.dnaty_version if tipo == "otimizado" else None}
    elif model_version_id:
        raise OtaError("model_version_id só vale para pacote de modelo.", status=422)

    guardado = storage.store.put(dados, "application/x-tar", namespace="ota")
    pacote = OtaPackage(
        kind=kind,
        version=version,
        sha256=_sha(dados),
        size_bytes=len(dados),
        storage_key=guardado.key,
        manifest={"kind": kind, "version": version, "sha256": _sha(dados),
                  "size_bytes": len(dados), "files": arquivos, "model": modelo},
        model_version_id=versao_modelo.id if versao_modelo else None,
        notes=notes,
        created_by=actor.id,
    )
    session.add(pacote)
    session.flush()
    audit.record(
        session, action="ota.package_published", subject_type=SubjectType.OTA_PACKAGE,
        subject_id=pacote.id, actor_type=ActorType.USER, actor_id=actor.id,
        actor_label=actor.email,
        model_version=f"{modelo['model_key']}@{modelo['version']}" if modelo else None,
        payload={"kind": kind, "version": version, "sha256": pacote.sha256,
                 "size_bytes": pacote.size_bytes},
    )
    return pacote


def destinar(
    session: Session,
    pacote: OtaPackage,
    *,
    actor: User,
    device_ids: list[str] | None = None,
    tenant_id: str | None = None,
) -> list[OtaDeployment]:
    """Cria um destino por robô. Robô que já tem destino aberto deste pacote é pulado."""
    if not device_ids and not tenant_id:
        raise OtaError("Informe os robôs (device_ids) ou o cliente (tenant_id).", status=422)
    consulta = select(Device)
    if device_ids:
        consulta = consulta.where(Device.id.in_(device_ids))
    if tenant_id:
        consulta = consulta.where(Device.tenant_id == tenant_id)
    robos = list(session.scalars(consulta.order_by(Device.serial_number)))
    if device_ids and len(robos) != len(set(device_ids)):
        raise OtaError("Robô não encontrado (ou de outro cliente que o informado).", status=404)
    if not robos:
        raise OtaError("Nenhum robô no alvo.", status=404)
    criados = []
    for robo in robos:
        if robo.status in (DeviceStatus.SUSPENDED, DeviceStatus.RETIRED,
                           DeviceStatus.UNPROVISIONED):
            raise OtaError(f"{robo.serial_number} está {robo.status.value}: não recebe pacote.")
        if pacote.kind == "model":
            versao = session.get(ModelVersion, pacote.model_version_id)
            if versao is None or versao.state is not ModelVersionState.PRODUCAO:
                raise OtaError("O modelo do pacote saiu de PRODUÇÃO: publique outro pacote.")
            liberadas = model_registry.chaves_liberadas(session, robo.tenant_id)
            if not model_registry.liberado(versao, liberadas):
                raise OtaError(f"{versao.model_key} não está liberado para o cliente de "
                               f"{robo.serial_number}.", status=403)
        aberto = session.scalar(select(OtaDeployment.id).where(
            OtaDeployment.package_id == pacote.id, OtaDeployment.device_id == robo.id,
            OtaDeployment.state.not_in(OTA_FINAL)))
        if aberto:
            continue
        agora = datetime.now(UTC)
        destino = OtaDeployment(tenant_id=robo.tenant_id, package_id=pacote.id,
                                device_id=robo.id, state="pendente", created_by=actor.id,
                                history=[{"at": agora.isoformat(), "state": "pendente",
                                          "by": actor.email}])
        session.add(destino)
        session.flush()
        corpo = {
            "deployment_id": destino.id,
            "device_id": robo.id,
            "package_id": pacote.id,
            "manifest": pacote.manifest,
            "issued_at": agora.isoformat(),
            "expires_at": (agora + VALIDADE_ENVELOPE).isoformat(),
        }
        destino.envelope = {"payload": corpo, "signature": signing.sign_ota(corpo),
                            "algorithm": signing.OTA_ALGORITHM}
        audit.record(
            session, action="ota.deployment_created", subject_type=SubjectType.DEVICE,
            subject_id=robo.id, tenant_id=robo.tenant_id, actor_type=ActorType.USER,
            actor_id=actor.id, actor_label=actor.email, new_state="pendente",
            payload={"deployment_id": destino.id, "package_id": pacote.id,
                     "kind": pacote.kind, "version": pacote.version},
        )
        criados.append(destino)
    return criados


def pendentes_do_robo(session: Session, device: Device) -> list[OtaDeployment]:
    return list(session.scalars(
        select(OtaDeployment)
        .where(OtaDeployment.device_id == device.id, OtaDeployment.state.not_in(OTA_FINAL))
        .order_by(OtaDeployment.created_at)
    ))


def destino_do_robo(session: Session, device: Device, deployment_id: str) -> OtaDeployment:
    destino = session.scalar(select(OtaDeployment).where(
        OtaDeployment.id == deployment_id, OtaDeployment.device_id == device.id))
    if destino is None:
        raise OtaError("Atualização não encontrada.", status=404)
    return destino


def trecho(session: Session, destino: OtaDeployment, offset: int, length: int) -> bytes:
    """Um pedaço do pacote (download com retomada: o robô pede do ponto em que parou)."""
    if destino.state in OTA_FINAL:
        raise OtaError(f"Atualização {destino.state}: nada a baixar.", status=410)
    pacote = session.get(OtaPackage, destino.package_id)
    if offset < 0 or length <= 0 or length > 8 * 2**20:
        raise OtaError("offset/length inválidos (length até 8 MB).", status=422)
    if offset >= pacote.size_bytes:
        return b""
    with storage.store.open(pacote.storage_key) as fh:
        fh.seek(offset)
        dados = fh.read(length)
    destino.bytes_served += len(dados)
    return dados


def informar(
    session: Session, device: Device, destino: OtaDeployment, estado: str,
    detalhe: str | None, versao_em_uso: str | None = None,
) -> OtaDeployment:
    if estado not in OTA_STATES:
        raise OtaError(f"Estado desconhecido: {estado}.", status=422)
    if estado == destino.state and estado != "baixando":
        return destino  # reenvio do mesmo estado: idempotente
    permitidos = TRANSICOES_DO_ROBO.get(destino.state, frozenset())
    if estado not in permitidos:
        raise OtaError(f"{destino.state} → {estado} não é uma transição válida.")
    anterior = destino.state
    agora = datetime.now(UTC)
    destino.state = estado
    destino.detail = (detalhe or "")[:2000] or None
    destino.history = [*destino.history, {"at": agora.isoformat(), "state": estado,
                                          "detail": destino.detail,
                                          "version_running": versao_em_uso}]
    if estado in OTA_FINAL:
        destino.finished_at = agora
    if estado != "baixando":
        audit.record(
            session, action=f"ota.{estado}", subject_type=SubjectType.DEVICE,
            subject_id=device.id, tenant_id=device.tenant_id, actor_type=ActorType.DEVICE,
            actor_id=device.id, actor_label=device.serial_number, old_state=anterior,
            new_state=estado, reason=destino.detail,
            payload={"deployment_id": destino.id, "package_id": destino.package_id,
                     "version_running": versao_em_uso},
        )
    if estado in OTA_FALHAS:
        # Vira aviso para o cliente e para a equipe (notificações, seção 48).
        pacote = session.get(OtaPackage, destino.package_id)
        events.publish(
            session, events.OTA_FAILED, tenant_id=device.tenant_id,
            subject_type=SubjectType.DEVICE, subject_id=device.id,
            payload={"deployment_id": destino.id, "state": estado, "detail": destino.detail,
                     "kind": pacote.kind if pacote else None,
                     "version": pacote.version if pacote else None},
        )
    return destino


def cancelar(session: Session, destino: OtaDeployment, *, actor: User) -> None:
    if destino.state in OTA_FINAL:
        raise OtaError(f"Atualização já {destino.state}.")
    if destino.state not in ("pendente", "baixando"):
        raise OtaError("O robô já está instalando: não dá para cancelar no meio "
                       "(ele termina ou volta sozinho).")
    anterior = destino.state
    destino.state = "cancelada"
    destino.finished_at = datetime.now(UTC)
    destino.history = [*destino.history, {"at": destino.finished_at.isoformat(),
                                          "state": "cancelada", "by": actor.email}]
    audit.record(
        session, action="ota.cancelada", subject_type=SubjectType.DEVICE,
        subject_id=destino.device_id, tenant_id=destino.tenant_id, actor_type=ActorType.USER,
        actor_id=actor.id, actor_label=actor.email, old_state=anterior, new_state="cancelada",
        payload={"deployment_id": destino.id},
    )


__all__ = ["OtaError", "artefato_do_robo", "cancelar", "destinar", "destino_do_robo",
           "informar", "ler_arquivo", "pendentes_do_robo", "publicar_pacote", "trecho"]
