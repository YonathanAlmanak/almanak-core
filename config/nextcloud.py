"""
Client Nextcloud minimal pour les widgets de l'Almanak.
Variables d'env requises dans /etc/almanak/almanak.env :
  NC_URL          https://cloud.entretablees.ca
  NC_USER         nom d'utilisateur Nextcloud (compte admin/bot)
  NC_APP_PASSWORD mot de passe d'application Nextcloud
"""
import logging
import os
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

NC_URL = os.environ.get("NC_URL", "").rstrip("/")
NC_USER = os.environ.get("NC_USER", "")
NC_APP_PASSWORD = os.environ.get("NC_APP_PASSWORD", "")

_AUTH = (NC_USER, NC_APP_PASSWORD)
_OCS = {"OCS-APIRequest": "true", "Accept": "application/json"}


def configured():
    return bool(NC_URL and NC_USER and NC_APP_PASSWORD)


def ecrire_dans_voute(nc_username: str, chemin_relatif: str, contenu: str) -> bool:
    """
    Écrit (ou écrase) un fichier texte dans la voûte Nextcloud d'un pionnier.

    Utilise les credentials admin/bot (NC_USER, NC_APP_PASSWORD). Fonctionne
    quand NC_USER est un compte admin sur l'instance Nextcloud cible.

    chemin_relatif : ex. "2-Projects/Mon profil Almanak.md" (sans slash initial)
    Retourne True si réussi, False sinon (ne lève jamais d'exception).
    """
    if not configured():
        return False
    try:
        import urllib.parse
        url = (
            f"{NC_URL}/remote.php/dav/files/"
            f"{urllib.parse.quote(nc_username, safe='')}/"
            f"{urllib.parse.quote(chemin_relatif, safe='/')}"
        )
        resp = requests.put(
            url,
            data=contenu.encode("utf-8"),
            auth=_AUTH,
            headers={"Content-Type": "text/markdown; charset=utf-8"},
            timeout=10,
        )
        if resp.status_code not in (200, 201, 204):
            logger.warning("ecrire_dans_voute %s/%s → HTTP %s", nc_username, chemin_relatif, resp.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("ecrire_dans_voute erreur : %s", exc)
        return False


def sur_la_table(limit=8):
    """
    Cartes de la colonne « Sur la table » dans le Deck Nextcloud.
    Retourne None si non configuré, [] si aucune carte trouvée.
    """
    if not configured():
        return None
    try:
        r = requests.get(
            f"{NC_URL}/apps/deck/api/v1/boards",
            auth=_AUTH, headers=_OCS, timeout=10,
        )
        r.raise_for_status()
        boards = r.json()

        board = None
        for b in boards:
            t = b.get("title", "").lower()
            if any(kw in t for kw in ("manac", "almanak", "neovillage")):
                board = b
                break
        if board is None and boards:
            board = boards[0]
        if board is None:
            return []

        r = requests.get(
            f"{NC_URL}/apps/deck/api/v1/boards/{board['id']}/stacks",
            auth=_AUTH, headers=_OCS, timeout=10,
        )
        r.raise_for_status()
        stacks = r.json()

        stack = None
        for s in stacks:
            if "table" in s.get("title", "").lower():
                stack = s
                break
        if stack is None:
            return []

        cards = stack.get("cards") or []
        return [
            {
                "title": c.get("title", ""),
                "description": (c.get("description") or "").strip()[:120],
            }
            for c in cards[:limit]
        ]
    except Exception:
        return []


def nouvelles_groupe(salon_token, limit=10):
    """
    Derniers messages texte du salon Talk désigné.
    Retourne None si non configuré, [] si erreur.
    """
    if not configured():
        return None
    try:
        r = requests.get(
            f"{NC_URL}/ocs/v2.php/apps/spreed/api/v1/chat/{salon_token}",
            params={"format": "json", "lookIntoFuture": 0, "limit": limit},
            auth=_AUTH, headers=_OCS, timeout=10,
        )
        r.raise_for_status()
        messages = r.json().get("ocs", {}).get("data", [])
        result = []
        for m in reversed(messages):
            if m.get("messageType") == "system":
                continue
            if not (m.get("message") or "").strip():
                continue
            ts = m.get("timestamp", 0)
            dt = datetime.fromtimestamp(ts).strftime("%-d %b %H:%M") if ts else ""
            result.append(
                {
                    "actor": m.get("actorDisplayName") or m.get("actorId", ""),
                    "message": m.get("message", ""),
                    "timestamp": dt,
                }
            )
        return result
    except Exception:
        return []
