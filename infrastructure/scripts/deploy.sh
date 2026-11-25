#!/bin/bash
# Déploiement sur /opt/almanak — à lancer en tant qu'almanak ou root
set -e

REPO="https://github.com/YonathanAlmanak/almanak-core.git"
APP_DIR="/opt/almanak"
VENV="$APP_DIR/venv"
RELEASE="$APP_DIR/releases/$(date +%Y%m%d_%H%M%S)"
CURRENT="$APP_DIR/current"
ENV_FILE="/etc/almanak/almanak.env"

echo "==> Clonage dans $RELEASE"
git clone --depth 1 "$REPO" "$RELEASE"

echo "==> Installation des dépendances"
"$VENV/bin/pip" install --quiet -r "$RELEASE/requirements.txt"

echo "==> Migrations"
cd "$RELEASE"
"$VENV/bin/python" manage.py migrate --settings=config.settings

echo "==> Fichiers statiques"
"$VENV/bin/python" manage.py collectstatic --no-input --settings=config.settings

echo "==> Bascule du lien current"
ln -sfn "$RELEASE" "$CURRENT"

echo "==> Redémarrage Gunicorn"
systemctl restart gunicorn

echo "==> Déploiement terminé : $RELEASE"
