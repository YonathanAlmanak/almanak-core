import requests as _http

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods

from config.nextcloud import nouvelles_groupe, sur_la_table, ecrire_dans_voute
from .models import UserProfile, Notification, Vouch

PIONNIER_ROOM = "b5zpbo3j"

QUESTIONS_ONBOARDING = [
    {"etape": 1, "champ": "nom_artiste",        "label": "Comment veux-tu être connu sur Almanak ?",          "aide": "Ton nom d'artiste ou ton prénom public",                        "type": "text",     "max": 100},
    {"etape": 2, "champ": "village",             "label": "Dans quel village ou territoire es-tu enraciné ?",  "aide": "Ex : Sainte-Émélie-de-l'Énergie, Lanaudière",                   "type": "text",     "max": 100},
    {"etape": 3, "champ": "photo",               "label": "Une photo qui te représente",                       "aide": "Visage, en action, ou ce que tu veux — JPEG/PNG/WebP, 5 Mo max", "type": "photo"},
    {"etape": 4, "champ": "bio_courte",          "label": "En quelques mots, qui es-tu ?",                    "aide": "Une ligne, 280 caractères max",                                  "type": "text",     "max": 280},
    {"etape": 5, "champ": "passions",            "label": "Qu'est-ce qui t'anime profondément ?",             "aide": "Tes passions, ce qui te fait sortir du lit le matin",             "type": "textarea"},
    {"etape": 6, "champ": "experience",          "label": "Qu'est-ce que tu fais dans la vie ?",              "aide": "Ton parcours, tes compétences, ce que tu apportes",               "type": "textarea"},
    {"etape": 7, "champ": "relations_cherchees", "label": "Qu'est-ce que tu cherches comme relations ?",      "aide": "Collaborateurs, mentors, clients, amis, partenaires…",            "type": "textarea"},
    {"etape": 8, "champ": "offre_culturelle",    "label": "Ton offre en une phrase",                          "aide": "Ce que tu proposes comme artiste, artisan ou entrepreneur",        "type": "text",     "max": 200},
]


def _profil(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


NC_BASE = "https://atelier.neovillage.org"


def _talk_iframe_ok(nc_server: str) -> bool:
    """Renvoie True si atelier.neovillage.org accepte l'embedding dans un iframe.
    Résultat mis en cache 1 heure pour éviter la latence à chaque requête."""
    cache_key = f"talk_iframe_ok_{nc_server}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = _http.head(
            f"https://{nc_server}/apps/spreed/",
            timeout=3, allow_redirects=True,
        )
        xfo = r.headers.get("X-Frame-Options", "").upper()
        result = "DENY" not in xfo and "SAMEORIGIN" not in xfo
    except Exception:
        result = False
    cache.set(cache_key, result, 3600)
    return result


VOUTE_STRUCTURE = ["1-Inbox", "2-Projects", "3-Casquettes", "4-Resources", "5-Archives"]


def _profil_vers_md(profile) -> str:
    """Génère le contenu Markdown du profil d'un pionnier pour sa voûte."""
    from django.utils.timezone import localdate
    aujourd_hui = localdate().isoformat()
    lignes = [
        "---",
        "type: profil",
        f"created: {aujourd_hui}",
        "status: actif",
        "---",
        "",
        f"# Mon profil Almanak",
        "",
    ]
    champs = [
        ("nom_artiste",        "Nom"),
        ("village",            "Village"),
        ("bio_courte",         "Bio"),
        ("passions",           "Passions"),
        ("experience",         "Expérience"),
        ("relations_cherchees","Relations cherchées"),
        ("offre_culturelle",   "Offre"),
    ]
    for attr, label in champs:
        valeur = (getattr(profile, attr, "") or "").strip()
        if valeur:
            lignes.append(f"**{label}** : {valeur}")
            lignes.append("")
    return "\n".join(lignes)


def _notifier(destinataires, type_notif, texte, lien=""):
    Notification.objects.bulk_create([
        Notification(user=u, type=type_notif, texte=texte, lien=lien)
        for u in destinataires
    ])


def notifier_nouveau_pionnier(nouveau_user):
    profile = UserProfile.objects.filter(user=nouveau_user).first()
    nom = (profile.nom_artiste if profile and profile.nom_artiste
           else nouveau_user.first_name or nouveau_user.username)
    village = f" de {profile.village}" if profile and profile.village else ""
    texte = f"{nom}{village} a rejoint le réseau."
    lien = f"/p/{nouveau_user.username}/"
    autres = User.objects.exclude(pk=nouveau_user.pk).filter(is_active=True)
    Notification.objects.bulk_create([
        Notification(user=u, type=Notification.NOUVEAU_PIONNIER, texte=texte, lien=lien)
        for u in autres
    ])


@login_required
def profil(request):
    profile = _profil(request.user)
    pionniers_recents = (
        UserProfile.objects
        .filter(onboarding_etape__gte=1)
        .exclude(user=request.user)
        .select_related("user")
        .order_by("-id")[:6]
    )
    return render(request, "profil.html", {
        "profile": profile,
        "voute_dossiers": VOUTE_STRUCTURE,
        "pionniers_recents": pionniers_recents,
        "sur_la_table": sur_la_table(),
        "nouvelles_groupe": nouvelles_groupe(PIONNIER_ROOM),
        "talk_url": f"{NC_BASE}/apps/spreed/#/call/{PIONNIER_ROOM}",
        "talk_room_lien": f"{NC_BASE}/call/{PIONNIER_ROOM}",
    })


@login_required
def onboarding(request):
    profile = _profil(request.user)

    if request.method == "POST":
        etape_post = int(request.POST.get("etape", 0))
        question = next((q for q in QUESTIONS_ONBOARDING if q["etape"] == etape_post), None)

        if question and question["type"] != "photo":
            champ = question["champ"]
            valeur = request.POST.get(champ, "").strip()
            max_len = question.get("max")
            if max_len:
                valeur = valeur[:max_len]
            setattr(profile, champ, valeur)

        if profile.onboarding_etape < etape_post:
            profile.onboarding_etape = etape_post
        profile.save()

        prochaine = etape_post + 1
        if prochaine > 8:
            if profile.nc_username:
                contenu = _profil_vers_md(profile)
                ecrire_dans_voute(profile.nc_username, "2-Projects/Mon profil Almanak.md", contenu)
            messages.success(request, "Ton profil est maintenant configuré !")
            return redirect("/profil/")
        return redirect(f"/onboarding/?etape={prochaine}")

    # GET : naviguer à une étape précise ou reprendre là où on en était
    etape = int(request.GET.get("etape", max(1, profile.onboarding_etape + 1)))
    etape = max(1, min(etape, 8))
    question = next((q for q in QUESTIONS_ONBOARDING if q["etape"] == etape), None)

    return render(request, "onboarding.html", {
        "question": question,
        "profile": profile,
        "etape": etape,
        "nb_questions": 8,
        "progression": int((etape - 1) / 8 * 100),
        "valeur_courante": getattr(profile, question["champ"], "") if question["type"] != "photo" else "",
    })


def profil_public(request, username):
    pionnier = get_object_or_404(User, username=username)
    profil_obj = _profil(pionnier)
    est_moi = request.user.is_authenticated and request.user == pionnier
    talk_salon = f"{NC_BASE}/call/{PIONNIER_ROOM}"
    nc_server = profil_obj.nc_server or "atelier.neovillage.org"
    talk_dm = (
        f"https://{nc_server}/apps/spreed/?callUser={profil_obj.nc_username}"
        if profil_obj.nc_username else None
    )
    # Passions comme liste de tags (séparées par virgule ou retour à la ligne)
    import re as _re
    passions_tags = []
    if profil_obj.passions:
        raw = profil_obj.passions.strip()
        passions_tags = [t.strip() for t in _re.split(r'[,\n]', raw) if t.strip()][:10]
    # Autres pionniers du même village
    meme_village = []
    if profil_obj.village:
        meme_village = (
            UserProfile.objects
            .filter(village__iexact=profil_obj.village)
            .exclude(user=pionnier)
            .select_related("user")
            .order_by("-id")[:4]
        )
    # Vouches + Orenda
    vouches = Vouch.objects.filter(cible=pionnier).select_related("source__profile")[:8]
    nb_vouches = Vouch.objects.filter(cible=pionnier).count()
    j_ai_vouche = (
        request.user.is_authenticated
        and not est_moi
        and Vouch.objects.filter(source=request.user, cible=pionnier).exists()
    )
    orenda = profil_obj.orenda_score()
    return render(request, "profil_public.html", {
        "pionnier": pionnier,
        "profil": profil_obj,
        "est_moi": est_moi,
        "est_connecte": request.user.is_authenticated,
        "talk_salon": talk_salon,
        "talk_dm": talk_dm,
        "passions_tags": passions_tags,
        "meme_village": meme_village,
        "vouches": vouches,
        "nb_vouches": nb_vouches,
        "j_ai_vouche": j_ai_vouche,
        "orenda": orenda,
    })


@login_required
@require_http_methods(["POST"])
def api_photo_upload(request):
    if "photo" not in request.FILES:
        return JsonResponse({"erreur": "Aucune photo"}, status=400)

    fichier = request.FILES["photo"]

    types_autorises = {"image/jpeg", "image/png", "image/webp"}
    if fichier.content_type not in types_autorises:
        return JsonResponse({"erreur": "Format non accepté (JPEG, PNG ou WebP)"}, status=400)

    if fichier.size > 5 * 1024 * 1024:
        return JsonResponse({"erreur": "Photo trop lourde (5 Mo max)"}, status=400)

    profile = _profil(request.user)
    if profile.photo:
        profile.photo.delete(save=False)

    profile.photo = fichier
    try:
        profile.save()
    except Exception as e:
        return JsonResponse({"erreur": f"Erreur lors de la sauvegarde : {e}"}, status=500)

    return JsonResponse({"ok": True, "url": profile.photo.url})


@login_required
@require_http_methods(["POST"])
def api_banniere_upload(request):
    if "banniere" not in request.FILES:
        return JsonResponse({"erreur": "Aucune image"}, status=400)

    fichier = request.FILES["banniere"]

    types_autorises = {"image/jpeg", "image/png", "image/webp"}
    if fichier.content_type not in types_autorises:
        return JsonResponse({"erreur": "Format non accepté (JPEG, PNG ou WebP)"}, status=400)

    if fichier.size > 8 * 1024 * 1024:
        return JsonResponse({"erreur": "Image trop lourde (8 Mo max)"}, status=400)

    profile = _profil(request.user)
    if profile.photo_banniere:
        profile.photo_banniere.delete(save=False)

    profile.photo_banniere = fichier
    try:
        profile.save()
    except Exception as e:
        return JsonResponse({"erreur": f"Erreur lors de la sauvegarde : {e}"}, status=500)

    return JsonResponse({"ok": True, "url": profile.photo_banniere.url})


@login_required
def notifications(request):
    notifs = Notification.objects.filter(user=request.user).order_by('-created')[:50]
    # Marquer toutes comme lues à la visite
    Notification.objects.filter(user=request.user, lu=False).update(lu=True)
    return render(request, "notifications.html", {"notifs": notifs})


@login_required
@require_http_methods(["POST"])
def api_notifs_lues(request):
    Notification.objects.filter(user=request.user, lu=False).update(lu=True)
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def api_vouch(request, username):
    cible = get_object_or_404(User, username=username)
    if cible == request.user:
        return JsonResponse({"erreur": "Tu ne peux pas te voucher toi-même."}, status=400)
    vouch, created = Vouch.objects.get_or_create(source=request.user, cible=cible)
    if created:
        # Notifier la cible
        profil_source = _profil(request.user)
        nom = profil_source.nom_artiste or request.user.first_name or request.user.username
        village = f" de {profil_source.village}" if profil_source.village else ""
        texte = f"{nom}{village} a confirmé sa confiance en toi."
        lien = f"/p/{request.user.username}/"
        Notification.objects.create(
            user=cible, type=Notification.NOUVEAU_PIONNIER,
            texte=texte, lien=lien,
        )
    nb = Vouch.objects.filter(cible=cible).count()
    return JsonResponse({"ok": True, "cree": created, "nb_vouches": nb})


@login_required
@require_http_methods(["POST"])
def api_unvouch(request, username):
    cible = get_object_or_404(User, username=username)
    Vouch.objects.filter(source=request.user, cible=cible).delete()
    nb = Vouch.objects.filter(cible=cible).count()
    return JsonResponse({"ok": True, "nb_vouches": nb})


@login_required
def messages(request):
    profile = _profil(request.user)
    nc_server = profile.nc_server or "atelier.neovillage.org"
    talk_messages_url = f"https://{nc_server}/apps/spreed/#/direct"
    talk_messages_lien = f"https://{nc_server}/apps/spreed/"
    return render(request, "messages.html", {
        "profile": profile,
        "talk_messages_url": talk_messages_url,
        "talk_messages_lien": talk_messages_lien,
        "iframe_ok": _talk_iframe_ok(nc_server),
    })


def pionniers(request):
    profils = (
        UserProfile.objects
        .filter(onboarding_etape__gte=1)
        .select_related("user")
        .order_by("-id")
    )
    return render(request, "pionniers.html", {
        "profils": profils,
        "est_connecte": request.user.is_authenticated,
    })


@login_required
def voutes(request):
    profile = _profil(request.user)
    return render(request, "voutes.html", {"profile": profile})


@login_required
def reglages(request):
    profile = _profil(request.user)
    section_active = request.GET.get("section", "nextcloud")

    if request.method == "POST":
        section = request.POST.get("section", "")

        if section == "nextcloud":
            profile.nc_username = request.POST.get("nc_username", "").strip()
            profile.nc_server = request.POST.get("nc_server", "atelier.neovillage.org").strip()
            profile.save()
            messages.success(request, "Voûte Nextcloud enregistrée.")
            return redirect("/reglages/?section=nextcloud")

        elif section == "motdepasse":
            actuel = request.POST.get("mot_de_passe_actuel", "")
            nouveau = request.POST.get("nouveau_mot_de_passe", "")
            confirmation = request.POST.get("confirmation_mot_de_passe", "")

            if not request.user.check_password(actuel):
                messages.error(request, "Mot de passe actuel incorrect.")
            elif len(nouveau) < 8:
                messages.error(request, "Le nouveau mot de passe doit avoir au moins 8 caractères.")
            elif nouveau != confirmation:
                messages.error(request, "Le nouveau mot de passe et la confirmation ne correspondent pas.")
            else:
                request.user.set_password(nouveau)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Mot de passe changé avec succès.")

            return redirect("/reglages/?section=motdepasse")

    return render(request, "reglages.html", {
        "profile": profile,
        "section_active": section_active,
    })
