#!/usr/bin/env bash
set -euo pipefail

# Sincroniza data/{rag,docs,media} al bucket R2 manteniendo la estructura

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"

# Carga solo variables R2_* desde .env (preferido) o .env.r2 (fallback)
load_r2_env() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  # Lee líneas tipo R2_KEY=valor, ignora comentarios y espacios iniciales
  while IFS='=' read -r key value; do
    # Salta líneas vacías o comentarios
    [[ -z "$key" ]] && continue
    [[ "$key" =~ ^# ]] && continue
    # Solo variables que inician con R2_
    if [[ "$key" =~ ^R2_[A-Za-z0-9_]+$ ]]; then
      # Quita comentarios al final de la línea si hay
      value="${value%%#*}"
      # Quita comillas envolventes si existen
      value="${value%\r}"
      value="${value%\n}"
      value="${value%\"}"
      value="${value#\"}"
      value="${value%\'}"
      value="${value#\'}"
      export "$key=$value"
    fi
  done < "$file"
}

if [[ -f "$ROOT_DIR/.env" ]]; then
  load_r2_env "$ROOT_DIR/.env" || true
elif [[ -f "$ROOT_DIR/.env.r2" ]]; then
  load_r2_env "$ROOT_DIR/.env.r2" || true
fi

# Normaliza variables según tu .env
# Soporta ambos estilos: *_ACCESS_KEY_ID / *_SECRET_ACCESS_KEY y R2_ACCESS_KEY / R2_SECRET_KEY
R2_BUCKET=${R2_BUCKET:-aura-storage}
R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID:-${R2_ACCESS_KEY:-}}
R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY:-${R2_SECRET_KEY:-}}
R2_ENDPOINT=${R2_ENDPOINT:-}
R2_ACCOUNT_ID=${R2_ACCOUNT_ID:-}

# Deriva endpoint si no está y hay ACCOUNT_ID
if [[ -z "$R2_ENDPOINT" && -n "$R2_ACCOUNT_ID" ]]; then
  R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
fi

usage() {
  cat <<EOF
Uso: $(basename "$0") [--dry-run]

Requisitos:
  - awscli instalado (aws --version)
  - Credenciales en .env (preferido) o .env.r2, o variables de entorno:
      Requeridos: R2_BUCKET, (R2_ENDPOINT o R2_ACCOUNT_ID), (R2_ACCESS_KEY o R2_ACCESS_KEY_ID), (R2_SECRET_KEY o R2_SECRET_ACCESS_KEY)

Sincroniza:
  data/rag   -> s3://$R2_BUCKET/rag
  data/docs  -> s3://$R2_BUCKET/docs
  data/media -> s3://$R2_BUCKET/media

Opciones:
  --dry-run   Muestra los cambios sin aplicar
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: awscli no encontrado. Instálalo (pipx/pip/brew) y reintenta." >&2
  exit 1
fi

if [[ -z "$R2_ENDPOINT" && -z "$R2_ACCOUNT_ID" ]]; then
  echo "Error: define R2_ENDPOINT o R2_ACCOUNT_ID en el entorno (.env)." >&2
  exit 1
fi

if [[ -z "$R2_BUCKET" ]]; then
  echo "Error: define R2_BUCKET en el entorno (.env)." >&2
  exit 1
fi

if [[ -z "$R2_ACCESS_KEY_ID" || -z "$R2_SECRET_ACCESS_KEY" ]]; then
  echo "Error: faltan credenciales R2. Define (R2_ACCESS_KEY/R2_ACCESS_KEY_ID) y (R2_SECRET_KEY/R2_SECRET_ACCESS_KEY)." >&2
  exit 1
fi

DRYRUN_FLAG=""
if [[ "${1:-}" == "--dry-run" ]]; then
  DRYRUN_FLAG="--dryrun"
fi

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"
export AWS_EC2_METADATA_DISABLED=true

ENDPOINT="$R2_ENDPOINT"
echo "Sincronizando hacia bucket: $R2_BUCKET (endpoint: $ENDPOINT)"

mkdir -p "$ROOT_DIR/data/rag" "$ROOT_DIR/data/docs" "$ROOT_DIR/data/media"

set -x
aws s3 sync "$ROOT_DIR/data/rag"   "s3://$R2_BUCKET/rag"   --endpoint-url "$ENDPOINT" --delete $DRYRUN_FLAG
aws s3 sync "$ROOT_DIR/data/docs"  "s3://$R2_BUCKET/docs"  --endpoint-url "$ENDPOINT" --delete $DRYRUN_FLAG
aws s3 sync "$ROOT_DIR/data/media" "s3://$R2_BUCKET/media" --endpoint-url "$ENDPOINT" --delete $DRYRUN_FLAG
set +x

echo "Listo."
