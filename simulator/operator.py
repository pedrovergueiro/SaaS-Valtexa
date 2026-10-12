"""Cliente do lado humano — o que o SaaS visual vai fazer por baixo.

Existe para provar uma afirmação da arquitetura: **não há rota privada de
frontend**. Tudo que uma tela faria, este cliente faz pelas mesmas rotas
públicas, com o mesmo token e sujeito às mesmas permissões. Quando o SaaS visual
for construído, ele substitui este arquivo e nada no servidor muda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


@dataclass
class OperatorClient:
    """Sessão de um usuário."""

    base_url: str
    token: str = ""
    tenant_id: str = ""
    role: str = ""
    capabilities: list[str] = field(default_factory=list)
    timeout: float = 30.0
    _http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._http = httpx.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout)

    @classmethod
    def login(
        cls, base_url: str, email: str, password: str, tenant: str | None = None
    ) -> OperatorClient:
        client = cls(base_url=base_url)
        body = client.post(
            "/v1/auth/login", {"email": email, "password": password, "tenant": tenant}
        )
        client.token = body["access_token"]
        client.tenant_id = body["tenant_id"] or ""
        client.role = body["role"] or ""
        client.capabilities = body["capabilities"]
        return client

    # --- transporte ---------------------------------------------------------
    @property
    def headers(self) -> dict[str, str]:
        head = {}
        if self.token:
            head["Authorization"] = f"Bearer {self.token}"
        if self.tenant_id:
            head["X-Tenant-Id"] = self.tenant_id
        return head

    def get(self, path: str, params: dict | None = None) -> dict | list:
        return self._send("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, params: dict | None = None) -> dict:
        return self._send("POST", path, json=json, params=params)

    def patch(self, path: str, json: dict | None = None) -> dict:
        return self._send("PATCH", path, json=json)

    def put(self, path: str, json: dict | None = None) -> dict:
        return self._send("PUT", path, json=json)

    def try_post(self, path: str, json: dict | None = None, params: dict | None = None) -> dict:
        """Como :meth:`post`, mas devolve o erro em vez de levantar.

        Usado no roteiro para demonstrar um bloqueio — que é um resultado
        esperado do sistema, não uma falha do simulador.
        """
        try:
            return self.post(path, json=json, params=params)
        except ApiError as exc:
            return {"error": True, "status_code": exc.status_code, "detail": exc.detail}

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OperatorClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _send(
        self, method: str, path: str, json: dict | None = None, params: dict | None = None
    ) -> dict | list:
        response = self._http.request(
            method, path, json=json, params=params, headers=self.headers
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(response.status_code, str(detail))
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()
