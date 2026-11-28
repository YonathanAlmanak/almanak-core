import json
import re
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib.auth import views as auth_views
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.conf.urls.static import static
from config.nextcloud import creer_voute_pioneer
from profiles.views import (
    profil, voutes, reglages, onboarding, profil_public,
    pionniers, mixer, messages, conversation, api_envoyer_message,
    questions, repondre_qdj,
    notifications, api_notifs_lues,
    api_vouch, api_unvouch,
    api_photo_upload, api_photo_action_upload, api_banniere_upload,
)

DATA             = Path("/opt/almanak/data")
APPROUVES        = DATA / "evenements.json"
BRUTS            = DATA / "evenements_bruts.json"
TOKEN_FILE       = DATA / ".admin_token"
REGISTRE_BIDOO   = DATA / "registre_bidoo.json"
NC_BOT_CREDS     = DATA / ".nc_bot_creds"
BABILLARD_FILE   = DATA / "babillard.json"
QDJ_FILE         = DATA / "question_du_jour.json"
NEXTCLOUD_BASE   = "https://atelier.neovillage.org"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lire_json(chemin, defaut=None):
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    return defaut if defaut is not None else {}


def _ecrire_json(chemin, data):
    chemin.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cors(response):
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Headers"] = "X-Admin-Token, Content-Type"
    return response


def _verifier_token(request):
    token_attendu = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
    token_recu = request.headers.get("X-Admin-Token", "")
    return token_attendu and token_recu == token_attendu


def _nc_bot_auth():
    if NC_BOT_CREDS.exists():
        parts = NC_BOT_CREDS.read_text(encoding="utf-8").strip().split(":", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
    return None, None


def _nc_creer_utilisateur(username, password, display_name="", email=""):
    bot_user, bot_pass = _nc_bot_auth()
    if not bot_user:
        return False, "Credentials du bot Nextcloud absents."
    payload = urllib.parse.urlencode({
        "userid": username, "password": password,
        "displayName": display_name or username, "email": email,
    }).encode()
    creds_b64 = base64.b64encode(f"{bot_user}:{bot_pass}".encode()).decode()
    req = urllib.request.Request(
        f"{NEXTCLOUD_BASE}/ocs/v1.php/cloud/users", data=payload, method="POST",
        headers={"Authorization": f"Basic {creds_b64}", "OCS-APIRequest": "true",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            if "<statuscode>100</statuscode>" in body:
                return True, ""
            m = re.search(r"<message>(.*?)</message>", body)
            return False, m.group(1) if m else body[:200]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        m = re.search(r"<message>(.*?)</message>", body)
        return False, m.group(1) if m else str(e)
    except Exception as e:
        return False, str(e)


# ── Pages ─────────────────────────────────────────────────────────────────────

def home(request):
    if request.user.is_authenticated:
        return redirect("/profil/")
    return render(request, "home.html")


GLYPHES = ['∅', '|', '∧', '✕', '⊏', '⋈']
CTX_BASE = {"glyphes": GLYPHES}

# Code Bidoo : 6 positions en 2 groupes de 3 (Lot · Unité), base 6
# num ∈ [1, 46 656]  (6^6)
def _bidoo_num(p1, p2, p3, p4, p5, p6):
    return p1*7776 + p2*1296 + p3*216 + p4*36 + p5*6 + p6 + 1


def rejoindre(request):
    if request.method == "GET":
        return render(request, "rejoindre.html", CTX_BASE)

    def _int_pos(key):
        try:
            v = int(request.POST.get(key, ""))
            return v if 0 <= v <= 5 else None
        except (ValueError, TypeError):
            return None

    etape = request.POST.get("etape", "1")

    # ── Étape 1 : vérifier le code Bidoo ─────────────────────────────────────
    if etape == "1":
        p1, p2, p3 = _int_pos("p1"), _int_pos("p2"), _int_pos("p3")
        p4, p5, p6 = _int_pos("p4"), _int_pos("p5"), _int_pos("p6")

        def err1(msg):
            return render(request, "rejoindre.html", {**CTX_BASE, "erreur": msg})

        if any(x is None for x in [p1, p2, p3, p4, p5, p6]):
            return err1("Code Bidoo incomplet — sélectionne les 6 glyphes.")

        num = _bidoo_num(p1, p2, p3, p4, p5, p6)

        if not REGISTRE_BIDOO.exists():
            return err1("Registre introuvable — contacter l'administrateur.")
        registre = _lire_json(REGISTRE_BIDOO, {"emis": []})
        entree = next((b for b in registre.get("emis", []) if int(b["virga"]) == num), None)

        if not entree:
            return err1("Ce code Bidoo ne correspond à aucun Bidoo émis.")
        if entree.get("utilise"):
            return err1("Ce Bidoo a déjà été utilisé pour créer un compte.")

        return render(request, "rejoindre.html", {
            **CTX_BASE,
            "prenom":    entree.get("prenom", ""),
            "bidoo_num": num,
        })

    # ── Étape 2 : créer le compte ─────────────────────────────────────────────
    bidoo_num_str = request.POST.get("bidoo_num", "")
    username  = request.POST.get("username", "").strip()
    password  = request.POST.get("password", "").strip()
    email     = request.POST.get("email", "").strip()
    temp_pass = request.POST.get("temp_pass", "").strip()

    try:
        num = int(bidoo_num_str)
        assert 1 <= num <= 46656
    except Exception:
        return render(request, "rejoindre.html", {**CTX_BASE, "erreur": "Session expirée. Recommence depuis le début."})

    if not REGISTRE_BIDOO.exists():
        return render(request, "rejoindre.html", {**CTX_BASE, "erreur": "Registre introuvable."})
    registre = _lire_json(REGISTRE_BIDOO, {"emis": []})
    entree = next((b for b in registre.get("emis", []) if int(b["virga"]) == num), None)

    prenom = entree.get("prenom", "") if entree else ""
    ctx2 = {**CTX_BASE, "prenom": prenom, "bidoo_num": num,
            "username": username, "email": email}

    def err2(msg):
        return render(request, "rejoindre.html", {**ctx2, "erreur": msg})

    if not entree:
        return err2("Bidoo introuvable. Recommence depuis le début.")
    if entree.get("utilise"):
        return err2("Ce Bidoo a déjà été utilisé.")
    if entree.get("temp_pass", "") != temp_pass:
        return err2("Mot de passe temporaire incorrect.")
    if not re.match(r"^[a-zA-Z0-9_\-]{3,30}$", username):
        return err2("Nom d'utilisateur : 3 à 30 caractères, lettres, chiffres, tirets et underscores.")
    if len(password) < 10:
        return err2("Le nouveau mot de passe doit avoir au moins 10 caractères.")
    if User.objects.filter(username=username).exists():
        return err2("Ce nom d'utilisateur est déjà pris.")

    # Créer le compte Nextcloud avec un mot de passe aléatoire (le pionnier ne le voit jamais)
    nc_password = secrets.token_urlsafe(32)
    ok, msg = _nc_creer_utilisateur(username=username, password=nc_password,
                                    display_name=prenom or username, email=email)
    if not ok:
        if "already" in msg.lower() or "exist" in msg.lower():
            return err2("Ce nom d'utilisateur est déjà pris.")
        return err2(f"Erreur lors de la création du compte : {msg}")

    # Marquer le Bidoo utilisé
    entree["utilise"]     = True
    entree["nc_username"] = username
    entree["temp_pass"]   = ""
    _ecrire_json(REGISTRE_BIDOO, registre)

    # Provisionner la voûte via le compte de service
    creer_voute_pioneer(username)

    # Créer le compte Django et connecter le pionnier directement
    from profiles.models import UserProfile
    from profiles.views import notifier_nouveau_pionnier
    django_user = User.objects.create_user(
        username=username, email=email,
        password=password,
        first_name=prenom or username,
    )
    profile, _ = UserProfile.objects.get_or_create(user=django_user)
    profile.nc_username    = username
    profile.nc_server      = "atelier.neovillage.org"
    profile.voute_initialisee = True
    profile.save()
    notifier_nouveau_pionnier(django_user)
    auth_login(request, django_user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("/onboarding/?etape=1")


# ── API événements ────────────────────────────────────────────────────────────

def api_evenements(request):
    return _cors(JsonResponse(_lire_json(APPROUVES, {"evenements": [], "nb_evenements": 0})))


def api_evenements_bruts(request):
    if not _verifier_token(request):
        return _cors(JsonResponse({"erreur": "Non autorisé"}, status=403))
    return _cors(JsonResponse(_lire_json(BRUTS, {"evenements": []})))


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def api_approuver(request, event_id):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))
    if not _verifier_token(request):
        return _cors(JsonResponse({"erreur": "Non autorisé"}, status=403))
    bruts    = _lire_json(BRUTS, {"evenements": []})
    approuves = _lire_json(APPROUVES, {"evenements": []})
    cible    = next((e for e in bruts["evenements"] if e.get("id") == event_id), None)
    if not cible:
        return _cors(JsonResponse({"erreur": "Introuvable"}, status=404))
    bruts["evenements"] = [e for e in bruts["evenements"] if e.get("id") != event_id]
    cible["statut"] = "approuve"
    approuves["evenements"].append(cible)
    approuves["nb_evenements"] = len(approuves["evenements"])
    bruts["nb_evenements"] = len(bruts["evenements"])
    _ecrire_json(BRUTS, bruts)
    _ecrire_json(APPROUVES, approuves)
    return _cors(JsonResponse({"ok": True, "id": event_id}))


@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def api_rejeter(request, event_id):
    if request.method == "OPTIONS":
        return _cors(JsonResponse({}))
    if not _verifier_token(request):
        return _cors(JsonResponse({"erreur": "Non autorisé"}, status=403))
    bruts = _lire_json(BRUTS, {"evenements": []})
    bruts["evenements"] = [e for e in bruts["evenements"] if e.get("id") != event_id]
    bruts["nb_evenements"] = len(bruts["evenements"])
    _ecrire_json(BRUTS, bruts)
    return _cors(JsonResponse({"ok": True, "id": event_id}))


# ── API Babillard ─────────────────────────────────────────────────────────────

@login_required
def api_babillard(request):
    if request.method == "GET":
        data = _lire_json(BABILLARD_FILE, {"posts": []})
        return JsonResponse(data)
    if request.method == "POST":
        try:
            body = json.loads(request.body)
            texte = body.get("texte", "").strip()[:600]
        except Exception:
            return JsonResponse({"erreur": "JSON invalide"}, status=400)
        if not texte:
            return JsonResponse({"erreur": "Texte vide"}, status=400)
        data = _lire_json(BABILLARD_FILE, {"posts": []})
        post = {
            "id": secrets.token_hex(6),
            "auteur": request.user.username,
            "auteur_display": request.user.first_name or request.user.username,
            "texte": texte,
            "date": datetime.utcnow().isoformat() + "Z",
        }
        data["posts"].insert(0, post)
        data["posts"] = data["posts"][:200]
        _ecrire_json(BABILLARD_FILE, data)
        # Notifier les autres membres
        from profiles.models import Notification
        nom_display = request.user.first_name or request.user.username
        extrait = texte[:80] + ("…" if len(texte) > 80 else "")
        autres = User.objects.exclude(pk=request.user.pk).filter(is_active=True)
        Notification.objects.bulk_create([
            Notification(
                user=u, type=Notification.BABILLARD,
                texte=f"{nom_display} sur le babillard : « {extrait} »",
                lien="/profil/#widget-babillard",
            )
            for u in autres
        ])
        return JsonResponse({"ok": True, "post": post})
    return JsonResponse({"erreur": "Méthode non supportée"}, status=405)


# ── API Question du jour ──────────────────────────────────────────────────────

def api_question_du_jour(request):
    data = _lire_json(QDJ_FILE, {"question": "", "date": "", "reponses": []})
    aujourd_hui = date.today().isoformat()
    if data.get("date") != aujourd_hui:
        data = {"question": data.get("question", ""), "date": data.get("date", ""), "reponses": []}
    return JsonResponse(data)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_question_repondre(request):
    try:
        body = json.loads(request.body)
        texte = body.get("texte", "").strip()[:600]
    except Exception:
        return JsonResponse({"erreur": "JSON invalide"}, status=400)
    if not texte:
        return JsonResponse({"erreur": "Texte vide"}, status=400)
    data = _lire_json(QDJ_FILE, {"question": "", "date": "", "reponses": []})
    if any(r["auteur"] == request.user.username for r in data.get("reponses", [])):
        return JsonResponse({"erreur": "Déjà répondu aujourd'hui"}, status=400)
    reponse = {
        "auteur": request.user.username,
        "auteur_display": request.user.first_name or request.user.username,
        "texte": texte,
        "date": datetime.utcnow().isoformat() + "Z",
    }
    data.setdefault("reponses", []).append(reponse)
    _ecrire_json(QDJ_FILE, data)
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
def api_verifier_temp_pass(request):
    try:
        body = json.loads(request.body)
        bidoo_num = int(body.get("bidoo_num", 0))
        temp_pass = body.get("temp_pass", "").strip()
    except Exception:
        return JsonResponse({"ok": False})
    if not temp_pass or not REGISTRE_BIDOO.exists():
        return JsonResponse({"ok": False})
    registre = _lire_json(REGISTRE_BIDOO, {"emis": []})
    entree = next((b for b in registre.get("emis", []) if int(b["virga"]) == bidoo_num), None)
    if not entree or entree.get("utilise"):
        return JsonResponse({"ok": False})
    return JsonResponse({"ok": entree.get("temp_pass", "") == temp_pass})


# ── Admin Bidoo ───────────────────────────────────────────────────────────────

GLYPHES_BIDOO = ['∅', '|', '∧', '✕', '⊏', '⋈']


def _bidoo_vers_glyphes(num):
    n = num - 1
    p = [n//7776, (n%7776)//1296, (n%1296)//216, (n%216)//36, (n%36)//6, n%6]
    lot   = ''.join(GLYPHES_BIDOO[x] for x in p[:3])
    unite = ''.join(GLYPHES_BIDOO[x] for x in p[3:])
    return f"{lot} · {unite}"


def _prochain_bidoo(registre):
    utilises = {int(b["virga"]) for b in registre.get("emis", [])}
    for n in range(1, 46657):
        if n not in utilises:
            return n
    return None


def _enrichir_bidoo(b):
    return {**b, "code": _bidoo_vers_glyphes(int(b["virga"]))}


def admin_bidoo(request):
    auteur = request.session.get("admin_bidoo_ok", False)
    flash = erreur = erreur_auth = None

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "auth":
            token_saisi = request.POST.get("token", "").strip()
            token_attendu = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
            if token_saisi and token_saisi == token_attendu:
                request.session["admin_bidoo_ok"] = True
                auteur = True
            else:
                erreur_auth = "Token incorrect."

        elif action == "creer" and auteur:
            prenom = request.POST.get("prenom", "").strip()[:40]

            def _int_p(key):
                try:
                    v = int(request.POST.get(key, ""))
                    return v if 0 <= v <= 5 else None
                except (ValueError, TypeError):
                    return None

            ps = [_int_p(f"p{i}") for i in range(1, 7)]

            if not prenom:
                erreur = "Le prénom est requis."
            elif any(x is None for x in ps):
                erreur = "Sélectionne les 6 glyphes du Bidoo."
            else:
                p1, p2, p3, p4, p5, p6 = ps
                num = _bidoo_num(p1, p2, p3, p4, p5, p6)
                registre = _lire_json(REGISTRE_BIDOO, {"emis": []})
                deja = any(int(b["virga"]) == num for b in registre.get("emis", []))
                if deja:
                    erreur = f"Le code {_bidoo_vers_glyphes(num)} est déjà attribué."
                else:
                    temp = secrets.token_urlsafe(8)
                    registre["emis"].append({"virga": num, "prenom": prenom, "temp_pass": temp, "utilise": False})
                    _ecrire_json(REGISTRE_BIDOO, registre)
                    flash = f"Bidoo créé pour {prenom} · Code : {_bidoo_vers_glyphes(num)} · Temp : {temp}"

    registre = _lire_json(REGISTRE_BIDOO, {"emis": []})
    tous = [_enrichir_bidoo(b) for b in registre.get("emis", [])]
    libres = [b for b in tous if not b.get("utilise")]
    utilises = [b for b in tous if b.get("utilise")]

    return render(request, "admin_bidoo.html", {
        "auteur": auteur,
        "libres": libres,
        "utilises": utilises,
        "nb_total": len(tous),
        "nb_libres": len(libres),
        "nb_utilises": len(utilises),
        "flash": flash,
        "erreur": erreur,
        "erreur_auth": erreur_auth,
    })


urlpatterns = [
    path("admin/", admin.site.urls),
    path("admin-bidoo/", admin_bidoo, name="admin_bidoo"),
    path("", home, name="home"),
    path("rejoindre/", rejoindre, name="rejoindre"),
    path("rejoindre/verifier-temp-pass/", api_verifier_temp_pass),
    path("connexion/", auth_views.LoginView.as_view(
        template_name="connexion.html",
        redirect_authenticated_user=True,
    ), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(next_page="/connexion/"), name="deconnexion"),
    path("profil/", profil, name="profil"),
    path("onboarding/", onboarding, name="onboarding"),
    path("pionniers/", pionniers, name="pionniers"),
    path("mixer/", mixer, name="mixer"),
    path("messages/", messages, name="messages"),
    path("messages/<str:username>/", conversation, name="conversation"),
    path("api/messages/<str:username>/envoyer/", api_envoyer_message),
    path("questions/", questions, name="questions"),
    path("questions/repondre/", repondre_qdj, name="repondre_qdj"),
    path("notifications/", notifications, name="notifications"),
    path("api/notifications/lues/", api_notifs_lues),
    path("api/vouch/<str:username>/", api_vouch, name="api_vouch"),
    path("api/unvouch/<str:username>/", api_unvouch, name="api_unvouch"),
    path("p/<str:username>/", profil_public, name="profil_public"),
    path("voutes/", voutes, name="voutes"),
    path("reglages/", reglages, name="reglages"),
    path("api/profil/photo/", api_photo_upload),
    path("api/profil/photo-action/", api_photo_action_upload),
    path("api/profil/banniere/", api_banniere_upload),
    # API événements
    path("api/evenements/", api_evenements),
    path("api/evenements/bruts/", api_evenements_bruts),
    path("api/evenements/approuver/<str:event_id>/", api_approuver),
    path("api/evenements/rejeter/<str:event_id>/", api_rejeter),
    # API Babillard
    path("api/babillard/", api_babillard),
    # API Question du jour
    path("api/question-du-jour/", api_question_du_jour),
    path("api/question-du-jour/repondre/", api_question_repondre),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
