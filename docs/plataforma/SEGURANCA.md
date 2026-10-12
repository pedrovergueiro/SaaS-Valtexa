# Segurança (brief, seções 36 e 43) — estado na Parte 9

> O que protege a plataforma, como cada coisa é testada, o **checklist** de produção e a
> **rotação** de segredos. Deploy: [`DEPLOY.md`](DEPLOY.md). Toda linha "teste" abaixo roda
> na suíte do SaaS (`cd saas && .venv/bin/pytest`).

## 1. Checklist de produção (seção 36)

Marque antes de abrir para cliente. **Em código** = a plataforma recusa subir sem isso.

| # | Item | Como | Em código? |
| --- | --- | --- | --- |
| 1 | `SESSION_SECRET`, `COMMAND_SIGNING_SECRET`, `OTA_SIGNING_SECRET`, `INFERENCE_SERVICE_TOKEN` presentes, ≥ 32 caracteres, sem palavra de modelo, **distintos entre si** | `deploy/producao/gerar-segredos.sh` | **sim** — API e worker não sobem (`test_segredos.py`) |
| 2 | `METRICS_TOKEN` diferente dos quatro acima | idem | **sim** |
| 3 | Segredos como **arquivo** (`/run/secrets`, `SECRETS_DIR`), não variável no compose nem no Git | compose de produção | leitura por arquivo: sim (`test_segredo_lido_de_arquivo_montado`) |
| 4 | Postgres (não SQLite) | `database_url` | **sim** |
| 5 | `CORS_ORIGINS` sem `*` | o domínio do console | **sim** |
| 6 | `SIMULATED_INFERENCE` desligado | — | **sim** |
| 7 | `REDIS_URL` (limite de taxa e travas entre réplicas) | compose | **sim** |
| 8 | `STORAGE_BACKEND=s3` com bucket **privado** (sem leitura pública), credencial só com as ações necessárias | política do bucket | bucket: **não** (passo de deploy) |
| 9 | TLS na borda com HSTS; `/metrics` não exposto à internet | `Caddyfile` | proxy: passo de deploy |
| 10 | IA só na rede interna, com `SERVICE_TOKEN` | compose (`ia` sem porta publicada) | token: sim (`test_token_de_servico.py`, `ia/tests/test_service_auth.py`) |
| 11 | `PLATFORM_ADMIN_PASSWORD` trocada no primeiro acesso | console | não |
| 12 | Backups do Postgres e do bucket, restauração testada | `DEPLOY.md` § 5 | não |
| 13 | Robôs: disco cifrado (LUKS), *secure boot*, chave privada só no robô | depende do hardware | não |
| 14 | Licença comercial do dNATY antes de servir modelo otimizado por ele | contrato | não |

## 2. Rotação de segredos

Os segredos são independentes: trocar um não exige trocar os outros. Gere o novo com
`openssl rand -base64 48`, grave no arquivo de `segredos/` (ou no cofre) e reinicie API e
worker (`docker compose up -d api worker`).

| Segredo | Efeito de trocar | Procedimento |
| --- | --- | --- |
| `SESSION_SECRET` (HMAC dos tokens de sessão) | todos os usuários e sessões de suporte são desconectados; robôs renovam o token de sessão sozinhos (assinatura Ed25519 continua valendo) | trocar e reiniciar; avisar os clientes. Para revogar **uma** pessoa, não rotacione: derrube as sessões dela (`/v1/auth/sessions`, `test_sessoes.py`) |
| `COMMAND_SIGNING_SECRET` (semente do par Ed25519 das missões) | a chave **pública** da plataforma muda; o robô a gravou no provisionamento → recusa toda missão nova até ser **reprovisionado**. Comandos em trânsito morrem (efeito desejado numa emergência) | rotação de emergência: trocar, reiniciar, reprovisionar a frota (token de provisionamento no console). **Falta**: rotação sem reprovisionar (o robô aceitar duas chaves por `key_id` — `COMMAND_SIGNING_KEY_ID` existe na plataforma, o robô guarda uma chave só) |
| `OTA_SIGNING_SECRET` | idem para os pacotes OTA (`ota_public_key` gravada no robô) | idem; pacotes já publicados precisam ser republicados |
| `INFERENCE_SERVICE_TOKEN` (= `SERVICE_TOKEN` da IA) | SaaS e IA precisam trocar juntos; entre um e outro, a IA recusa (o pipeline repete depois) | gravar o arquivo e reiniciar `ia`, `api`, `worker`, `prometheus` no mesmo comando |
| `METRICS_TOKEN` | o Prometheus para de raspar até ler o novo | reiniciar `api` e `prometheus` |
| `database_url` / senha do Postgres | — | `ALTER ROLE valtexa PASSWORD '…'`, gravar `postgres_password` e `database_url`, reiniciar `api` e `worker` |
| Senha do Redis | balde e travas recomeçam (inofensivo) | `redis_password` + `redis_url`, reiniciar `redis`, `api`, `worker` |
| Credencial do S3/MinIO | — | nova chave no provedor, `aws_credentials`, reiniciar `api`/`worker`; depois apagar a antiga |
| Credencial de **um robô** | — | `POST /v1/devices/{id}/revoke-credentials` corta na hora (`test_seguranca_parte9.py::test_credencial_revogada_para_sync_e_upload_na_hora`) e reprovisiona |

## 3. Testes de segurança (seção 43) — o que existe e onde

| Assunto | O que é provado | Teste |
| --- | --- | --- |
| Acesso cruzado entre clientes | **toda** rota do OpenAPI, com cada papel do cliente atacante, contra um recurso real da vítima: 404/403, nada vaza nem muda | `test_isolamento_openapi.py` (gerado do OpenAPI: rota nova entra sozinha — inclusive as `.../url` desta parte) |
| Escalada de privilégio | papel do cliente não alcança rota da plataforma; gestor não cria dono; ninguém muda o próprio papel; capacidades de plataforma não vêm de papel | `test_isolamento_openapi.py`, `test_plataforma_e_suporte.py`, `test_collections.py::TestFronteira` |
| Permissões (RBAC) | só agrônomo aprova aplicação; auditor/visualizador só leem | `test_security.py::TestRbac` |
| Sessões | expiração do token; **sessão vencida no servidor cai mesmo com token válido** (P9); revogação na hora, logout, troca de senha, reset pelo admin; token sem `sid` recusado; sessão revogada cai também nas rotas de arquivo (P9) | `test_security.py`, `test_sessoes.py`, `test_seguranca_parte9.py::TestSessoes` |
| Login | limite por conta e por IP, sem oráculo de e-mail | `test_limite_de_login.py`, `test_security.py` |
| Tokens | adulterado, sem assinatura, expirado; token de dispositivo não serve em rota de usuário | `test_security.py` |
| Impersonation (suporte) | motivo obrigatório, prazo com teto, só leitura por padrão, escrita só no modo assistido e auditada, **sessão vencida encerrada como "expirou"**, não atravessa cliente nem vale em rota de plataforma, o cliente vê quem entrou | `test_plataforma_e_suporte.py` |
| Upload de arquivos | tipo pela **assinatura dos bytes** (P9: HTML com extensão `.jpg` é recusado na coleta e na observação), tipo fora da lista recusado, tamanho maior que o declarado recusado, nome com `../` não vira caminho (chave por hash), corpo acima do teto → 413 **antes** da autenticação (P9) | `test_seguranca_parte9.py::TestUpload`, `::TestCorpoGrande`, `test_collections.py`, `test_storage.py` |
| Arquivo servido não executa | toda resposta de arquivo com `CSP: sandbox` e `nosniff`; tipo fora da lista vira `attachment` (P9); `nosniff` e `X-Frame-Options: DENY` em toda resposta (P9) | `test_seguranca_parte9.py::TestRespostaDeArquivo` |
| Acesso ao storage | sem URL pública; URL assinada só depois do escopo; outro cliente → 404; **URL adulterada para o objeto de outro cliente ou com validade esticada é inválida**; URL vence (P9) | `test_producao_s3.py::TestUrlAssinada` (verificador SigV4 independente) |
| Modelos | só versão em PRODUÇÃO com hash do registry vai ao robô; robô recusa pacote adulterado; cliente não alcança o registry | `test_ota.py`, `test_model_registry.py`, `rover/tests/test_ota.py`, `rover/tests/test_model_manager.py` |
| Endpoints do Rover | sem assinatura / credencial desconhecida recusados; **replay da mesma requisição** recusado (nonce), **corpo trocado depois de assinar**, **gravação antiga fora da janela**, **chave de um robô com assinatura de outro**, **credencial revogada corta sync, chunk e complete** (P9); limite por robô (429) somado entre réplicas (P9) | `test_security.py`, `test_seguranca_parte9.py::TestRover`, `test_hardening.py`, `test_coordenacao.py` |
| Comando assinado | alterado, chave alheia, vencido, destinatário | `test_security.py::TestCommandSigning`, `rover/tests/test_mission_command.py` |
| Segredos | produção recusa vazio/padrão/curto/de exemplo/repetido; varredura do repositório por chave privada e token de nuvem | `test_segredos.py` |

## 4. Achados e correções desta parte

| Onde | Problema | Correção | Teste que falha sem ela |
| --- | --- | --- | --- |
| `api/middleware.py` | o corpo de **qualquer** `/v1/device/*` era lido inteiro para a memória **antes** de autenticar, sem teto (negação de serviço por memória) | teto `MAX_ASSET_MB` + 1 MB, 413 pelo `Content-Length` ou ao passar do teto lendo | `TestCorpoGrande` |
| coletas e observação do robô | o tipo declarado era conferido, o conteúdo não: HTML com nome `.jpg` entrava como imagem | tipo pela assinatura dos bytes (JPEG/PNG/WebP/TIFF); o guardado é o real | `TestUpload` |
| rotas de arquivo | arquivo servido com o tipo gravado, sem `nosniff` nem CSP, na origem do console | `api/arquivos.py`: só tipos da lista saem inline; CSP `sandbox`; `nosniff` global | `TestRespostaDeArquivo` |
| CSV do relatório (console) | nome de fazenda/talhão começando com `=`/`+`/`-`/`@` virava fórmula no Excel | prefixo `'` (número negativo preservado) | `reportExport.test.ts` |
| `main.py` | a API não subia com `STORAGE_BACKEND=s3` (`store.root`) | `storage.preparar()` | `test_producao_s3.py::test_subida_da_api_com_s3_nao_procura_pasta` |
| `config.py` | `INFERENCE_SERVICE_TOKEN` só exigido com inferência ligada; segredo curto ou repetido com o token passava; worker subia sem checar | regra única para os quatro, API e worker | `test_segredos.py` |

## 5. O que não está coberto (honesto)

- **Rotação de chave do robô sem reprovisionar** (§ 2).
- **Cifra em repouso** do banco e do bucket é do provedor (RDS/S3 cifram por padrão; no
  MinIO do compose, configurar KMS/SSE — não feito).
- **WAF / limite por IP na borda**: o Caddy do compose não limita taxa por IP; o login tem
  limite próprio (banco) e os robôs, o balde (Redis).
- **Varredura de dependências** (pip-audit/npm audit) não roda na CI.
- **Pentest externo** não foi feito.
