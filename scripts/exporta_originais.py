"""Exporta os originais de uma missão do Rover, um arquivo por resultado: ``<record_id>.jpg``.

É a ponte para o treino com fotos de campo (``training.import_campo`` em VALTEXA-B): o
registro do Rover na IA chama cada quadro pelo ``record_id`` (o ``frame_id`` da fusão),
e os recortes saem dos originais que o Rover processou — já com a lente corrigida.

    python scripts/exporta_originais.py --mission <id> --dest originais/
    # depois, em VALTEXA-B:
    python -m training.import_campo --labels rotulos.csv \\
        --registro fields/plantas/registro/<talhão>.jsonl --originais originais/ \\
        --out data/coffee-campo

Só sai o que subiu em original: em missão de validação, rode o Rover em **modo coleta**
(``retencao.normal_sample_every = 1``), senão o quadro normal sobe reduzido (320 px) e
não serve para treino. Respeita o consentimento: cliente sem consentimento de treino
vigente não exporta nada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from valtexa import db
from valtexa.models import Asset, EdgeRecord, EdgeUpload, Mission
from valtexa.services import consent, storage


def exporta(session, mission_id: str, destino: Path) -> dict[str, int]:
    missao = session.get(Mission, mission_id)
    if missao is None:
        raise SystemExit(f"Missão {mission_id} não existe.")
    if not consent.permite_treino(session, missao.tenant_id):
        raise SystemExit("O cliente não autorizou uso das imagens para treino: nada exportado.")
    destino.mkdir(parents=True, exist_ok=True)
    feitos = faltam = 0
    for registro in session.scalars(select(EdgeRecord).where(
            EdgeRecord.mission_id == mission_id, EdgeRecord.kind == "result")):
        up = session.scalars(select(EdgeUpload).where(
            EdgeUpload.device_id == registro.device_id,
            EdgeUpload.record_id == registro.record_id, EdgeUpload.role == "original",
            EdgeUpload.status == "complete")).first()
        asset = session.get(Asset, up.asset_id) if up is not None and up.asset_id else None
        if asset is None:
            faltam += 1
            continue
        (destino / f"{registro.record_id}.jpg").write_bytes(storage.store.read(asset.storage_key))
        feitos += 1
    return {"exportados": feitos, "sem_original": faltam}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mission", required=True)
    p.add_argument("--dest", type=Path, required=True)
    args = p.parse_args(argv)
    with db.SessionLocal() as session:
        print(exporta(session, args.mission, args.dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
