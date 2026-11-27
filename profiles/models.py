from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    nc_username = models.CharField(max_length=150, blank=True)
    nc_server = models.CharField(max_length=255, blank=True, default='atelier.neovillage.org')

    def __str__(self):
        return f"Profil de {self.user.username}"
