from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from config.nextcloud import nouvelles_groupe, sur_la_table

PIONNIER_ROOM = "b5zpbo3j"


@login_required
def profil(request):
    return render(
        request,
        "profil.html",
        {
            "sur_la_table": sur_la_table(),
            "nouvelles_groupe": nouvelles_groupe(PIONNIER_ROOM),
        },
    )
