import json
import requests as _http

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods

from config.nextcloud import nouvelles_groupe, sur_la_table, ecrire_dans_voute
from .models import UserProfile, Notification, Vouch, Conversation, MessageDirect, ReponseQDJ, QUESTIONS_QDJ

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


def _carte_intro(profil_a, profil_b):
    """Génère une phrase d'accroche entre deux pionniers (v0.1 — règles de profil)."""
    nom_a = profil_a.nom_artiste or profil_a.user.username
    nom_b = profil_b.nom_artiste or profil_b.user.username

    if profil_a.village and profil_b.village:
        if profil_a.village.strip().lower() == profil_b.village.strip().lower():
            return f"{nom_a} et {nom_b} sont tous les deux enracinés à {profil_a.village}."

    if profil_a.passions and profil_b.passions:
        mots_a = set(w.lower().strip(".,;:!?") for w in profil_a.passions.split() if len(w) > 4)
        mots_b = set(w.lower().strip(".,;:!?") for w in profil_b.passions.split() if len(w) > 4)
        communs = mots_a & mots_b
        if communs:
            mot = sorted(communs, key=len, reverse=True)[0]
            return f"{nom_a} et {nom_b} ont tous les deux mentionné « {mot} » dans leur profil."

    if profil_b.village:
        return (f"{nom_a} ({profil_a.village or '?'}) et {nom_b} ({profil_b.village}) "
                f"— deux pionniers du réseau de confiance Almanak.")
    return f"{nom_a} et {nom_b} — deux pionniers du réseau de confiance Almanak."


def _conv_liste(user):
    """Retourne la liste des conversations d'un utilisateur, triée par dernier message."""
    convs = (
        Conversation.objects
        .filter(Q(user1=user) | Q(user2=user))
        .select_related('user1__profile', 'user2__profile')
    )
    items = []
    for c in convs:
        autre = c.autre(user)
        dernier = c.dernier_message()
        try:
            ap = autre.profile
        except UserProfile.DoesNotExist:
            ap = None
        items.append({
            'conv': c,
            'autre': autre,
            'autre_profile': ap,
            'dernier': dernier,
            'nb_non_lus': c.nb_non_lus(user),
        })
    items.sort(
        key=lambda x: x['dernier'].created if x['dernier'] else x['conv'].created,
        reverse=True,
    )
    return items


@login_required
def messages(request):
    conv_list = _conv_liste(request.user)
    return render(request, "messages.html", {
        "conv_list": conv_list,
        "conversation_active": None,
    })


@login_required
def conversation(request, username):
    autre_user = get_object_or_404(User, username=username)
    if autre_user == request.user:
        return redirect('/messages/')

    conv = Conversation.entre(request.user, autre_user)

    if request.method == 'POST':
        corps = request.POST.get('corps', '').strip()
        if corps and len(corps) <= 2000:
            MessageDirect.objects.create(conversation=conv, auteur=request.user, corps=corps)
            try:
                nom_moi = request.user.profile.nom_artiste or request.user.username
            except UserProfile.DoesNotExist:
                nom_moi = request.user.username
            Notification.objects.create(
                user=autre_user,
                type=Notification.MESSAGE,
                texte=f"Nouveau message de {nom_moi}",
                lien=f"/messages/{request.user.username}/",
            )
        return redirect(f'/messages/{username}/')

    conv.messages_conv.filter(lu=False).exclude(auteur=request.user).update(lu=True)

    messages_fil = list(conv.messages_conv.select_related('auteur__profile').all())

    nb_mes_messages = sum(1 for m in messages_fil if m.auteur == request.user)
    carte_intro = None
    if nb_mes_messages == 0:
        try:
            carte_intro = _carte_intro(request.user.profile, autre_user.profile)
        except UserProfile.DoesNotExist:
            pass

    conv_list = _conv_liste(request.user)
    for item in conv_list:
        item['active'] = item['conv'].id == conv.id

    try:
        autre_profile = autre_user.profile
    except UserProfile.DoesNotExist:
        autre_profile = None

    try:
        vouch_donne = Vouch.objects.filter(source=request.user, cible=autre_user).exists()
    except Exception:
        vouch_donne = False

    reponses_qdj = list(
        ReponseQDJ.objects.filter(user=autre_user, publie=True).order_by('-created')[:3]
    )
    ma_prochaine_question = _prochaine_question(request.user)

    return render(request, "messages.html", {
        "conv_list": conv_list,
        "conversation_active": conv,
        "autre_user": autre_user,
        "autre_profile": autre_profile,
        "messages_fil": messages_fil,
        "carte_intro": carte_intro,
        "vouch_donne": vouch_donne,
        "reponses_qdj": reponses_qdj,
        "ma_prochaine_question": ma_prochaine_question,
    })


@login_required
@require_http_methods(["POST"])
def api_envoyer_message(request, username):
    autre_user = get_object_or_404(User, username=username)
    if autre_user == request.user:
        return JsonResponse({"erreur": "Impossible de s'écrire à soi-même."}, status=400)

    try:
        data = json.loads(request.body)
        corps = data.get('corps', '').strip()
    except (json.JSONDecodeError, ValueError):
        corps = request.POST.get('corps', '').strip()

    if not corps:
        return JsonResponse({'erreur': 'Message vide.'}, status=400)
    if len(corps) > 2000:
        return JsonResponse({'erreur': 'Message trop long (max 2000 caractères).'}, status=400)

    conv = Conversation.entre(request.user, autre_user)
    msg = MessageDirect.objects.create(conversation=conv, auteur=request.user, corps=corps)

    try:
        nom_moi = request.user.profile.nom_artiste or request.user.username
    except UserProfile.DoesNotExist:
        nom_moi = request.user.username
    Notification.objects.create(
        user=autre_user,
        type=Notification.MESSAGE,
        texte=f"Nouveau message de {nom_moi}",
        lien=f"/messages/{request.user.username}/",
    )

    return JsonResponse({
        'ok': True,
        'id': msg.id,
        'corps': msg.corps,
        'created': msg.created.isoformat(),
        'auteur': request.user.username,
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


# ── Questions du jour (Vox Pop interne) ──────────────────────────────────────

def _question_par_id(qid):
    return next((q for q in QUESTIONS_QDJ if q['id'] == qid), None)


def _prochaine_question(user):
    """Retourne la prochaine question sans réponse pour cet utilisateur."""
    repondues = set(
        ReponseQDJ.objects.filter(user=user).values_list('question_id', flat=True)
    )
    for q in QUESTIONS_QDJ:
        if q['id'] not in repondues:
            return q
    return None


def questions(request):
    """Feed TikTok-style des réponses publiées."""
    reponses = (
        ReponseQDJ.objects.filter(publie=True)
        .select_related('user__profile')
        .order_by('-created')[:60]
    )
    prochaine = None
    if request.user.is_authenticated:
        prochaine = _prochaine_question(request.user)
    if prochaine is None:
        prochaine = QUESTIONS_QDJ[0]

    q_active = request.GET.get('q')
    if q_active:
        reponses = reponses.filter(question_id=q_active)

    return render(request, 'questions.html', {
        'reponses': reponses,
        'prochaine_question': prochaine,
        'toutes_questions': QUESTIONS_QDJ,
        'q_active': q_active,
    })


@login_required
def repondre_qdj(request):
    qid = request.POST.get('question_id') or request.GET.get('q', QUESTIONS_QDJ[0]['id'])
    question = _question_par_id(qid)
    if not question:
        return redirect('/questions/')

    if request.method == 'POST':
        corps = request.POST.get('corps', '').strip()[:1200]
        citation = request.POST.get('citation', '').strip()[:280]
        video = request.FILES.get('video')

        if not corps and not video:
            return render(request, 'repondre_qdj.html', {
                'question': question,
                'toutes_questions': QUESTIONS_QDJ,
                'erreur': 'Écris ta réponse ou envoie une vidéo.',
            })

        defaults = {
            'question_texte': question['texte'],
            'corps': corps,
            'citation': citation or corps[:180],
            'publie': True,
        }
        rep, created = ReponseQDJ.objects.get_or_create(
            user=request.user,
            question_id=qid,
            defaults=defaults,
        )
        if not created:
            rep.corps = corps
            rep.citation = citation or corps[:180]
            if video:
                rep.video = video
            rep.save()

        messages.success(request, "Réponse publiée ✦")
        return redirect('/questions/')

    # GET — afficher le formulaire
    existante = ReponseQDJ.objects.filter(user=request.user, question_id=qid).first()
    return render(request, 'repondre_qdj.html', {
        'question': question,
        'toutes_questions': QUESTIONS_QDJ,
        'existante': existante,
    })
