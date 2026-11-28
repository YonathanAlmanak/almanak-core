#!/bin/bash
# Déploiement sur /opt/almanak — à lancer en tant que root
set -e

ENV_FILE="/etc/almanak/almanak.env"
APP_DIR="/opt/almanak"
VENV="$APP_DIR/venv"
RELEASE="$APP_DIR/releases/$(date +%Y%m%d_%H%M%S)"
CURRENT="$APP_DIR/current"
REPO="https://github.com/YonathanAlmanak/almanak-core.git"

# Charger les variables d'environnement (DB_PASSWORD, SECRET_KEY, etc.)
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "AVERTISSEMENT : $ENV_FILE introuvable"
fi

echo "==> Clonage dans $RELEASE"
git clone --depth 1 "$REPO" "$RELEASE"

echo "==> Dossier media persistant"
MEDIA_DIR="$APP_DIR/data/media"
mkdir -p "$MEDIA_DIR/photos" "$MEDIA_DIR/bannieres" "$MEDIA_DIR/qdj/videos" "$MEDIA_DIR/qdj/thumbnails"
chown -R almanak:almanak "$MEDIA_DIR"
ln -sfn "$MEDIA_DIR" "$RELEASE/media"

echo "==> Installation des dépendances"
"$VENV/bin/pip" install --quiet -r "$RELEASE/requirements.txt"

echo "==> Migrations"
"$VENV/bin/python" "$RELEASE/manage.py" migrate --settings=config.settings

echo "==> Fichiers statiques"
"$VENV/bin/python" "$RELEASE/manage.py" collectstatic --no-input --settings=config.settings

echo "==> Bascule du lien current"
ln -sfn "$RELEASE" "$CURRENT"

echo "==> Redémarrage Gunicorn"
systemctl restart gunicorn

echo "==> Déploiement terminé : $RELEASE"
