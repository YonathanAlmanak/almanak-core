from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def profil(request):
    return render(request, 'profil.html')
