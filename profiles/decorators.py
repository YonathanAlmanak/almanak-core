from functools import wraps
from django.shortcuts import redirect
from .models import UserProfile


def role_required(minimum_role):
    """
    Restreint une vue aux utilisateurs ayant au moins le rôle donné.
    Hiérarchie : member < admin < superadmin
    """
    _hierarchy = {UserProfile.MEMBER: 0, UserProfile.ADMIN: 1, UserProfile.SUPERADMIN: 2}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('/connexion/')
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if _hierarchy.get(profile.role, 0) < _hierarchy.get(minimum_role, 0):
                return redirect('/profil/')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
