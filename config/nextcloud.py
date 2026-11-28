"""
Client Nextcloud minimal pour les widgets de l'Almanak.
Variables d'env requises dans /etc/almanak/almanak.env :
  NC_URL          https://cloud.entretablees.ca
  NC_USER         nom d'utilisateur Nextcloud (compte admin/bot)
  NC_APP_PASSWORD mot de passe d'application Nextcloud
"""
import logging
import os
from datetime import datetime, timezone

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


def creer_voute_pioneer(nc_username: str) -> bool:
    """
    Crée la structure standard Almanak dans la voûte Nextcloud d'un pionnier.

    Dossiers créés :
      Almanak/
        1-Inbox/
        2-Projects/
        3-Casquettes/
        4-Resources/
        5-Archives/
    + Almanak/Bienvenue.md

    Retourne True si réussi (ou déjà existant), False sinon.
    """
    if not configured():
        return False
    try:
        import urllib.parse
        base = f"{NC_URL}/remote.php/dav/files/{urllib.parse.quote(nc_username, safe='')}"

        dossiers = [
            "Almanak",
            "Almanak/1-Inbox",
            "Almanak/2-Projects",
            "Almanak/3-Casquettes",
            "Almanak/4-Resources",
            "Almanak/5-Archives",
        ]

        for dossier in dossiers:
            url = f"{base}/{urllib.parse.quote(dossier, safe='/')}"
            resp = requests.request("MKCOL", url, auth=_AUTH, timeout=10)
            # 201 = créé, 405 = existe déjà — les deux sont acceptables
            if resp.status_code not in (201, 405):
                logger.warning("creer_voute_pioneer MKCOL %s/%s → HTTP %s", nc_username, dossier, resp.status_code)

        bienvenue = f"""---
type: bienvenue
created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
---

# Bienvenue dans ta voûte, {nc_username} !

Ta voûte Almanak est maintenant prête.

- **1-Inbox/** — tes captures rapides, idées brutes, notes à trier
- **2-Projects/** — tes projets actifs (un sous-dossier par projet)
- **3-Casquettes/** — tes rôles récurrents (Artiste, Entrepreneur, Parent…)
- **4-Resources/** — tes références externes, lectures, inspirations
- **5-Archives/** — tes projets terminés ou en pause

Une idée par note. Une note = un concept.
"""
        ecrire_dans_voute(nc_username, "Almanak/Bienvenue.md", bienvenue)
        return True
    except Exception as exc:
        logger.warning("creer_voute_pioneer erreur : %s", exc)
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
