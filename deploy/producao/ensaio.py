"""Ensaio de produção sem Docker (Parte 9): duas réplicas da API, S3, Redis, segredos por arquivo.

Pré-requisitos (ver docs/DEPLOY.md § 6): Postgres, ``redis-server`` com senha, um S3
(MinIO, AWS ou ``moto_server``), a pasta de segredos de ``gerar-segredos.sh`` com
``database_url``, ``redis_url`` e ``aws_credentials`` apontando para eles, as variáveis de
produção exportadas (as mesmas do compose) e, com elas, duas APIs nas portas 8091 e 8092
(``uvicorn valtexa.main:app --port 8091`` e ``8092``) e o worker. Então, de ``saas/``:

    python ../deploy/producao/ensaio.py /caminho/da/pasta-que-contem/segredos

Para o limite somado entre réplicas, suba as APIs com ``DEVICE_RATE_PER_MINUTE=30``.
"""

import hashlib
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, ".")
from tests.helpers import DeviceSession, provision
from valtexa.services import edge_sync

E = Path(sys.argv[1])
A = httpx.Client(base_url="http://127.0.0.1:8091", timeout=30)
B = httpx.Client(base_url="http://127.0.0.1:8092", timeout=30)
ok = []


def passo(t, cond, det=""):
    ok.append(bool(cond))
    print(("✓" if cond else "✗"), t, det, flush=True)


def login(c, email, senha):
    r = c.post("/v1/auth/login", json={"email": email, "password": senha})
    r.raise_for_status()
    b = r.json()
    h = {"Authorization": f"Bearer {b['access_token']}"}
    if b.get("tenant_id"):
        h["X-Tenant-Id"] = b["tenant_id"]
    return h


senha = (E / "segredos/platform_admin_password").read_text()
from valtexa.seed import PLATFORM_TEAM  # noqa: E402

sa = login(A, next(iter(PLATFORM_TEAM)), senha)
sfx = datetime.now(UTC).strftime("%H%M%S")
cad = B.post(
    "/v1/admin/tenants",
    headers=sa,
    json={
        "tenant": {
            "name": "Ensaio Produção",
            "slug": f"ensaio-{sfx}",
            "contact_name": "P",
            "email": "p@ex.dev",
        },
        "farm": {"name": "Fazenda Ensaio", "center_lat": -21.9, "center_lon": -45.8},
        "field": {
            "name": "T1",
            "crop": "coffee",
            "boundary": [
                [-45.801, -21.901],
                [-45.799, -21.901],
                [-45.799, -21.899],
                [-45.801, -21.899],
                [-45.801, -21.901],
            ],
        },
    },
)
passo(
    "cliente criado na réplica B com o token emitido pela A",
    cad.status_code == 201,
    cad.status_code,
)
cad = cad.json()
tenant = cad["tenant"]["id"]
ses = A.post(
    "/v1/platform/support-sessions",
    headers=sa,
    json={"tenant_id": tenant, "reason": "Ensaio de produção"},
).json()
tok = {"Authorization": f"Bearer {ses['access_token']}"}
B.post(
    f"/v1/platform/support-sessions/{ses['session']['id']}/mode",
    headers=tok,
    json={"mode": "assistido", "reason": "Cadastrar gestor"},
).raise_for_status()
A.post(
    "/v1/users",
    headers=tok,
    json={
        "email": f"gestor{sfx}@ensaio.dev",
        "full_name": "Gestor",
        "password": "senha-do-ensaio-2026",
        "role": "admin",
    },
).raise_for_status()
gestor = {**login(B, f"gestor{sfx}@ensaio.dev", "senha-do-ensaio-2026"), "X-Tenant-Id": tenant}
robo = provision(A, gestor, "ROVER_SCOUT_V1", f"ENS-{sfx}", cad["farm_id"])
passo("robô provisionado (par Ed25519 gerado no robô)", bool(robo.device_id))


def via(c):  # mesmo robô, outra réplica
    return DeviceSession(c, robo.device_id, robo.key_id, robo.private_key)


corpo = {
    "id": "ev-1",
    "kind": "event",
    "type": "IMAGE_EVENT_DETECTED",
    "device_id": robo.device_id,
    "field_id": cad["field_id"],
    "occurred_at": datetime.now(UTC).isoformat(),
    "payload": {"label": "Rust", "confidence": 0.9},
}
r = via(B).request(
    "POST",
    "/v1/device/edge/records",
    json_body={
        "records": [
            {
                "id": "ev-1",
                "kind": "event",
                "type": "IMAGE_EVENT_DETECTED",
                "sha256": edge_sync.canonical_sha256(corpo),
                "body": corpo,
            }
        ]
    },
)
passo(
    "registro da Edge AI aceito",
    r.status_code == 200 and r.json()["accepted"] == ["ev-1"],
    r.text[:80],
)

dados = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 400  # ~100 KB, 7 chunks de 16 KB
sha = hashlib.sha256(dados).hexdigest()
n = 16384
ab = via(A).request(
    "POST",
    "/v1/device/uploads",
    json_body={
        "upload_id": "up-1",
        "sha256": sha,
        "size_bytes": len(dados),
        "content_type": "image/jpeg",
        "chunk_size": n,
        "record_id": "ev-1",
        "role": "original",
        "tier": "ORIGINAL",
        "priority": 2,
    },
)
total = ab.json()["total_chunks"]
cods = [
    via(A if i % 2 else B)
    .request(
        "PUT",
        f"/v1/device/uploads/up-1/chunks/{i}",
        content=dados[i * n : (i + 1) * n],
        headers={"Content-Type": "application/octet-stream"},
    )
    .status_code
    for i in range(total)
]
passo(f"{total} chunks alternando A/B", cods == [200] * total, cods)
estado = via(A).request("GET", "/v1/device/uploads/up-1").json()
passo("a réplica A vê os chunks que chegaram na B", estado["received_chunks"] == list(range(total)))
fim = via(B).request("POST", "/v1/device/uploads/up-1/complete", json_body={"sha256": sha})
passo(
    "complete na réplica B monta o arquivo do bucket",
    fim.status_code == 200 and fim.json()["status"] == "complete",
    fim.status_code,
)

recs = A.get("/v1/edge/records", headers=gestor).json()
pk = next(x["id"] for x in recs if x["record_id"] == "ev-1")
link = B.get(f"/v1/edge/records/{pk}/files/up-1/url", headers=gestor).json()
baixado = httpx.get(link["url"]).content
passo(
    "URL assinada (SigV4, 300 s) baixa o original do S3",
    link["direct"] and baixado == dados and "X-Amz-Signature" in link["url"],
)
via_api = A.get(f"/v1/edge/records/{pk}/files/up-1", headers=gestor)
passo(
    "rota da API serve inerte (CSP sandbox, nosniff)",
    via_api.content == dados and "sandbox" in via_api.headers["content-security-policy"],
)

# Limite por robô somado entre réplicas (DEVICE_RATE_PER_MINUTE=30 no ensaio)
outro = provision(B, gestor, "ROVER_SCOUT_V1", f"ENS2-{sfx}", cad["farm_id"])
cod = [
    DeviceSession(A if i % 2 else B, outro.device_id, outro.key_id, outro.private_key)
    .request("GET", "/v1/device/uploads/nada")
    .status_code
    for i in range(36)
]
passo(
    "limite de 30/min vale para a soma das duas réplicas",
    cod.count(404) == 30 and cod[30:] == [429] * 6,
    f"{cod.count(404)} atendidas, {cod.count(429)} x 429",
)
sk = socket.create_connection(("127.0.0.1", 8091))
sk.sendall(
    b"POST /v1/device/edge/records HTTP/1.1\r\nHost: x\r\nContent-Length: 10000000000\r\n\r\n"
    + b"x" * 1000
)
resp = sk.recv(200).decode(errors="replace")
sk.close()
passo(
    "corpo de 10 GB declarado: 413 antes de autenticar",
    " 413 " in resp.split("\r\n")[0],
    resp.split("\r\n")[0],
)
print(f"\n{sum(ok)} de {len(ok)} passos ok")
