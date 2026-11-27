# Encyclopédie du développement — Almanak

Lexique vivant pour Yonathan et Steve. Chaque concept expliqué dans notre contexte, avec un exemple tiré du vrai code d'Almanak.

---

## C

### Codé en dur (*hardcoded*)

Une valeur écrite directement dans le code au lieu d'être calculée ou lue depuis une source externe (base de données, profil de l'utilisateur, fichier de configuration).

**Problème :** si la valeur doit changer selon la situation (l'utilisateur connecté, l'environnement, le moment), un code en dur force tout le monde à partager la même valeur figée.

**Exemple dans Almanak :**
```python
# ❌ Codé en dur — tous les pionniers voient le même salon Nextcloud
salon = "b5zpbo3j"

# ✅ Dynamique — chaque pionnier voit son propre salon
salon = request.user.profile.nc_username
```

**À retenir :** quand tu te demandes « est-ce que ça devrait changer selon qui se connecte, ou selon l'environnement ? », la réponse oui = ne pas coder en dur.

---

## D

### Décorateur (*decorator*)

Fonction Python qui enveloppe une autre fonction pour lui ajouter un comportement, sans modifier son code. Se place sur la ligne au-dessus avec `@`.

**Exemple dans Almanak (`profiles/decorators.py`) :**
```python
@role_required('admin')
def vue_admin(request):
    ...  # cette vue est protégée automatiquement
```

Le décorateur `@role_required('admin')` vérifie le rôle avant d'exécuter la vue. Si l'utilisateur n'a pas le bon rôle, il est redirigé — sans qu'on répète ce test dans chaque vue.

---

## D

### Déploiement (*deploy*)

Envoyer une nouvelle version du code du poste local vers le serveur en production, pour que les visiteurs voient les changements.

**Protocole Almanak (ne jamais déroger) :**
1. Modifier en local dans `C:\Users\jonat\almanak-core\`
2. `git add -A && git commit -m "description claire"`
3. `git push` → le code part vers GitHub (`YonathanAlmanak/almanak-core`)
4. SSH sur le serveur OVH → `bash /opt/almanak/current/infrastructure/scripts/deploy.sh`

**Règle d'or :** si ce n'est pas sur GitHub, ça n'existe pas. On ne modifie jamais directement sur le serveur.

---

## M

### Modèle (*model*)

Dans Django, un modèle est la description d'une table de base de données, écrite en Python. Chaque classe = une table, chaque attribut = une colonne.

**Exemple dans Almanak (`profiles/models.py`) :**
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    nc_username = models.CharField(max_length=100, blank=True)
```

Chaque pionnier a un `UserProfile` lié à son compte Django, qui stocke son rôle et son nom d'utilisateur Nextcloud.

---

## P

### Processeur de contexte (*context processor*)

Fonction Python qui injecte automatiquement des variables dans tous les gabarits HTML de Django, sans avoir à les passer manuellement dans chaque vue.

**Exemple dans Almanak (`profiles/context_processors.py`) :**
```python
def user_role(request):
    if request.user.is_authenticated:
        return {'user_role': request.user.profile.role}
    return {}
```

Grâce à ce processeur, le gabarit `base.html` peut afficher le badge de rôle du pionnier connecté sur toutes les pages, sans répéter le code dans chaque vue.

---

## V

### Vue (*view*)

Dans Django, une vue est la fonction qui reçoit une requête HTTP et retourne une réponse (une page HTML, une redirection, du JSON…). C'est le chef d'orchestre : il lit la base de données, prépare les données, et choisit quel gabarit afficher.

**Exemple simplifié :**
```python
def profil(request):
    pionnier = request.user.profile       # lit la base de données
    return render(request, 'profil.html', {'pionnier': pionnier})  # répond avec une page
```

---

*Ajouter un concept : ouvrir ce fichier, trouver la bonne lettre alphabétique, insérer l'entrée.*
