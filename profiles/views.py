from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from config.nextcloud import nouvelles_groupe, sur_la_table
from .models import UserProfile

PIONNIER_ROOM = "b5zpbo3j"


def _profil(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
def profil(request):
    return render(request, "profil.html", {
        "sur_la_table": sur_la_table(),
        "nouvelles_groupe": nouvelles_groupe(PIONNIER_ROOM),
    })


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
