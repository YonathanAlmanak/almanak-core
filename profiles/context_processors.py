from .models import UserProfile, Notification


def user_profile(request):
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        nb_notifs = Notification.objects.filter(user=request.user, lu=False).count()
        return {'user_profile': profile, 'nb_notifications': nb_notifs}
    return {'user_profile': None, 'nb_notifications': 0}
