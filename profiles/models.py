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

    # Widgets masqués sur le tableau de bord (IDs séparés par des virgules)
    widgets_caches = models.CharField(max_length=500, blank=True, default='')

    # Voûte Nextcloud — True si la structure Almanak/ a été créée
    voute_initialisee = models.BooleanField(default=False)

    # Voûte fédérée (Lot 2) — Nextcloud externe du pionnier
    nc_externe_url = models.CharField(max_length=255, blank=True)
    nc_externe_token = models.CharField(max_length=500, blank=True)  # Application Password NC

    # Profil "agence d'artistes" — champ privé (jamais affiché publiquement)
    saboteur = models.TextField(blank=True)

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


class Conversation(models.Model):
    """Échange direct 1:1 entre deux pionniers."""
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations_initiees')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations_recues')
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user1', 'user2')
        ordering = ['-created']

    @classmethod
    def entre(cls, user_a, user_b):
        u1, u2 = sorted([user_a, user_b], key=lambda u: u.id)
        conv, _ = cls.objects.get_or_create(user1=u1, user2=u2)
        return conv

    def autre(self, user):
        return self.user2 if self.user1 == user else self.user1

    def dernier_message(self):
        return self.messages_conv.order_by('-created').first()

    def nb_non_lus(self, user):
        return self.messages_conv.filter(lu=False).exclude(auteur=user).count()

    def __str__(self):
        return f"{self.user1.username} ↔ {self.user2.username}"


class MessageDirect(models.Model):
    """Message dans une conversation 1:1."""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages_conv')
    auteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages_envoyes')
    corps = models.TextField()
    lu = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created']

    def __str__(self):
        return f"[{self.auteur.username}] {self.corps[:60]}"


QUESTIONS_QDJ = [
    {"id": "medaille",  "texte": "Quel voisin mérite une médaille, et pourquoi ?"},
    {"id": "ici",       "texte": "Qu'est-ce qui te garde ici, dans ton village ?"},
    {"id": "matin",     "texte": "Qu'est-ce qui te fait sortir du lit le matin ?"},
    {"id": "projet",    "texte": "Un projet qui te tient à cœur en ce moment ?"},
    {"id": "cherche",   "texte": "Qu'est-ce que tu cherches comme collaborateurs ou alliés ?"},
    {"id": "fierte",    "texte": "Quelle est ta plus grande fierté de la dernière année ?"},
    {"id": "vision",    "texte": "Dans dix ans, à quoi ressemble ton village idéal ?"},
    {"id": "obstacle",  "texte": "Quel est le plus grand obstacle que tu as surmonté ?"},
    {"id": "offre",     "texte": "Qu'est-ce que tu peux offrir à ton réseau de confiance ?"},
    {"id": "renaissance", "texte": "Si tu pouvais rebâtir une chose dans ton village, ce serait quoi ?"},
]


class ReponseQDJ(models.Model):
    """Réponse d'un pionnier à une Question du jour (texte ou vidéo)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reponses_qdj')
    question_id = models.CharField(max_length=50)
    question_texte = models.CharField(max_length=300)
    corps = models.TextField(blank=True)
    citation = models.CharField(max_length=280, blank=True)
    video = models.FileField(upload_to='qdj/videos/', blank=True)
    thumbnail = models.ImageField(upload_to='qdj/thumbnails/', blank=True)
    publie = models.BooleanField(default=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created']
        unique_together = ('user', 'question_id')

    def type_reponse(self):
        return 'video' if self.video else 'texte'

    def extrait(self):
        return self.citation or (self.corps[:160] + '…' if len(self.corps) > 160 else self.corps)

    def __str__(self):
        return f"[{self.user.username}] {self.question_id}"


class Notification(models.Model):
    NOUVEAU_PIONNIER = 'nouveau_pionnier'
    BABILLARD = 'babillard'
    MESSAGE = 'message'
    TYPE_CHOICES = [
        (NOUVEAU_PIONNIER, 'Nouveau pionnier'),
        (BABILLARD, 'Babillard'),
        (MESSAGE, 'Message direct'),
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
