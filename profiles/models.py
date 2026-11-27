from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    MEMBER = 'member'
    ADMIN = 'admin'
    SUPERADMIN = 'superadmin'
    ROLE_CHOICES = [
        (MEMBER, 'Membre'),
        (ADMIN, 'Admin'),
        (SUPERADMIN, 'Superadmin'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    nc_username = models.CharField(max_length=150, blank=True)
    nc_server = models.CharField(max_length=255, blank=True, default='atelier.neovillage.org')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=MEMBER)

    def is_admin(self):
        return self.role in (self.ADMIN, self.SUPERADMIN)

    def is_superadmin(self):
        return self.role == self.SUPERADMIN

    def __str__(self):
        return f"Profil de {self.user.username} ({self.role})"
