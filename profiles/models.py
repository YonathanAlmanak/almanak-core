from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

    # Champs de profil public (alimentent la vitrine /p/<username>/)
    photo = models.ImageField(upload_to='photos/', blank=True)
    photo_banniere = models.ImageField(upload_to='bannieres/', blank=True)
    nom_artiste = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    bio_courte = models.CharField(max_length=280, blank=True)
    passions = models.TextField(blank=True)
    experience = models.TextField(blank=True)
    relations_cherchees = models.TextField(blank=True)
    offre_culturelle = models.TextField(blank=True)

    # Suivi de l'onboarding : 0 = pas commencé, 1–8 = étape courante, 9 = terminé
    onboarding_etape = models.PositiveSmallIntegerField(default=0)

    def pourcentage_profil(self):
        champs_texte = ['nom_artiste', 'village', 'bio_courte', 'passions',
                        'experience', 'relations_cherchees', 'offre_culturelle']
        remplis = sum(1 for c in champs_texte if getattr(self, c, '').strip())
        if self.photo:
            remplis += 1
        return int(remplis / 8 * 100)

    def orenda_score(self):
        """Score de confiance v0.1 : présence (20) + profil (30) + vouches reçus (50)."""
        from profiles.models import Vouch
        nb_vouches = Vouch.objects.filter(cible=self.user).count()
        pts_vouches = min(nb_vouches * 8, 50)
        pts_profil = int(self.pourcentage_profil() * 0.30)
        return 20 + pts_profil + pts_vouches

    def is_admin(self):
        return self.role in (self.ADMIN, self.SUPERADMIN)

    def is_superadmin(self):
        return self.role == self.SUPERADMIN

    def __str__(self):
        return f"Profil de {self.user.username} ({self.role})"


class Notification(models.Model):
    NOUVEAU_PIONNIER = 'nouveau_pionnier'
    BABILLARD = 'babillard'
    TYPE_CHOICES = [
        (NOUVEAU_PIONNIER, 'Nouveau pionnier'),
        (BABILLARD, 'Babillard'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=NOUVEAU_PIONNIER)
    texte = models.CharField(max_length=255)
    lien = models.CharField(max_length=255, blank=True)
    lu = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"[{self.type}] {self.user.username} — {self.texte[:60]}"


class Vouch(models.Model):
    """Un pionnier confirme sa confiance envers un autre (1 seul vouch par paire)."""
    source = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vouches_donnes')
    cible = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vouches_recus')
    message = models.CharField(max_length=280, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('source', 'cible')
        ordering = ['-created']

    def __str__(self):
        return f"{self.source.username} → {self.cible.username}"
