#!/bin/sh
# Gera ./segredos/* com valores aleatórios fortes (uma vez por instalação).
# Não sobrescreve arquivo que já existe: rodar de novo é seguro. Rotação: docs/SEGURANCA.md.
set -eu
cd "$(dirname "$0")"
umask 077
mkdir -p segredos
novo() { [ -s "segredos/$1" ] || openssl rand -base64 48 | tr -d '\n/+=' | head -c 64 > "segredos/$1"; }
for s in session_secret command_signing_secret ota_signing_secret inference_service_token \
         metrics_token postgres_password redis_password minio_root_password \
         platform_admin_password; do
  novo "$s"
done
[ -s segredos/minio_root_user ] || printf 'valtexa' > segredos/minio_root_user
[ -s segredos/database_url ] || printf 'postgresql+psycopg://valtexa:%s@db:5432/valtexa' \
  "$(cat segredos/postgres_password)" > segredos/database_url
[ -s segredos/redis_url ] || printf 'redis://:%s@redis:6379/0' \
  "$(cat segredos/redis_password)" > segredos/redis_url
[ -s segredos/aws_credentials ] || printf '[default]\naws_access_key_id = %s\naws_secret_access_key = %s\n' \
  "$(cat segredos/minio_root_user)" "$(cat segredos/minio_root_password)" > segredos/aws_credentials
echo "segredos em $(pwd)/segredos (fora do Git). Guarde uma cópia no cofre da empresa."
