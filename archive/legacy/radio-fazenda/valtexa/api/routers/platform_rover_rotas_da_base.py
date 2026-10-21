"""Rotas retiradas de valtexa/api/routers/platform_rover.py em 20/10/2026 (rádio/base arquivados).

Trechos copiados como estavam; para recuperar, cole de volta no roteador (com os imports de
``chave_de_enlace``, ``cobertura_talhao``, ``estacao_base``, ``DeviceKind`` e ``Field as Talhao``)."""

# --- modelo de entrada ---
class ChaveDeEnlaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

# --- equipe ---
@router.get("/platform/bases", summary="Bases da fazenda: internet, filas, rádios, Rovers")
def lista_bases(tenant_id: str | None = None, caller: PlatformCaller = Depends(LER),
                session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [{**estacao_base.resumo(b), "talhoes": cobertura_talhao.talhoes_da_base(session, b)}
            for b in estacao_base.bases(session, tenant_id)]


@router.get("/platform/bases/{device_id}", summary="Uma base da fazenda")
def uma_base(device_id: str, caller: PlatformCaller = Depends(LER),
             session: Session = Depends(get_session)) -> dict[str, Any]:
    base = next((b for b in estacao_base.bases(session) if b.id == device_id), None)
    if base is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Base não encontrada.")
    return {**estacao_base.resumo(base),
            "talhoes": cobertura_talhao.talhoes_da_base(session, base)}


@router.get("/platform/fields/{field_id}/cobertura",
            summary="O mapa de cobertura do rádio de um talhão (o último levantamento da base)")
def cobertura_do_talhao(field_id: str, caller: PlatformCaller = Depends(LER),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    talhao = session.get(Talhao, field_id)
    if talhao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.")
    return {"field_id": talhao.id, "name": talhao.name, "mapa": talhao.cobertura,
            "cobertura_em": talhao.cobertura_em.isoformat() if talhao.cobertura_em else None}


# --- robô / base ---
@router.put("/device/enlace/chave",
            summary="O robô publica a chave do rádio da fazenda (assinada pela identidade dele)")
def device_enlace_chave(payload: ChaveDeEnlaceIn, caller: DeviceCaller = Depends(current_device),
                        session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        salvo = chave_de_enlace.publica(session, caller.device, caller.credential,
                                        payload.model_dump())
    except chave_de_enlace.ChaveInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return salvo


@router.get("/device/base/pares",
            summary="A base da fazenda busca as chaves de rádio dos robôs que ela atende")
def device_base_pares(caller: DeviceCaller = Depends(current_device),
                      session: Session = Depends(get_session)) -> dict[str, Any]:
    if caller.device.model is None or caller.device.model.kind != DeviceKind.GATEWAY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só a base da fazenda busca as chaves.")
    return chave_de_enlace.pares_da_base(session, caller.device)


@router.put("/device/base/cobertura/{field_id}",
            summary="A base manda o mapa de cobertura do rádio de um talhão (levantamento)")
def device_base_cobertura(field_id: str, payload: dict[str, Any],
                          caller: DeviceCaller = Depends(current_device),
                          session: Session = Depends(get_session)) -> dict[str, Any]:
    if caller.device.model is None or caller.device.model.kind != DeviceKind.GATEWAY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só a base da fazenda manda cobertura.")
    talhao = session.get(Talhao, field_id)
    try:
        if talhao is None:
            raise LookupError
        mapa = cobertura_talhao.guarda(session, caller.device, talhao, payload)
    except LookupError as exc:  # 404 também para talhão de outro cliente: não dá pista
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talhão não encontrado.") from exc
    except cobertura_talhao.CoberturaInvalidaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return {"field_id": talhao.id, "contagem": mapa["contagem"],
            "zonas_mortas": len(mapa["zonas_mortas"])}


