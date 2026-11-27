from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods

from config.nextcloud import nouvelles_groupe, sur_la_table
from .models import UserProfile

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


@login_required
def profil(request):
    profile = _profil(request.user)
    return render(request, "profil.html", {
        "profile": profile,
        "sur_la_table": sur_la_table(),
        "nouvelles_groupe": nouvelles_groupe(PIONNIER_ROOM),
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
    return render(request, "profil_public.html", {
        "pionnier": pionnier,
        "profil": profil_obj,
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
def voutes(request):
    profile = _profil(request.user)
    return render(request, "voutes.html", {"profile": profile})


@login_required
def reglages(request):
    profile = _profil(request.user)
    if request.method == "POST":
        section = request.POST.get("section", "")
        if section == "nextcloud":
            profile.nc_username = request.POST.get("nc_username", "").strip()
            profile.nc_server = request.POST.get("nc_server", "atelier.neovillage.org").strip()
            profile.save()
            messages.success(request, "Voûte Nextcloud enregistrée.")
        return redirect("/reglages/")
    return render(request, "reglages.html", {"profile": profile})
