import io
import tempfile
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile


def _image_jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (200, 200), color='#3b5d42').save(buf, format='JPEG')
    buf.seek(0)
    return SimpleUploadedFile('photo.jpg', buf.read(), content_type='image/jpeg')


MEDIA_TMP = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class PhotoUploadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testpionnier', password='testpass123')
        self.client.login(username='testpionnier', password='testpass123')

    def test_profil_accessible_connecte(self):
        r = self.client.get('/profil/')
        self.assertEqual(r.status_code, 200)

    def test_profil_redirige_non_connecte(self):
        self.client.logout()
        r = self.client.get('/profil/')
        self.assertRedirects(r, '/connexion/?next=/profil/')

    def test_upload_photo_valide(self):
        r = self.client.post('/api/profil/photo/', {'photo': _image_jpeg()})
        self.assertEqual(r.status_code, 200)
        from profiles.models import UserProfile
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(bool(profile.photo))

    def test_upload_format_invalide(self):
        f = SimpleUploadedFile('script.exe', b'MZmalware', content_type='application/octet-stream')
        r = self.client.post('/api/profil/photo/', {'photo': f})
        self.assertEqual(r.status_code, 400)

    def test_upload_sans_fichier(self):
        r = self.client.post('/api/profil/photo/', {})
        self.assertEqual(r.status_code, 400)

    def test_upload_trop_lourd(self):
        gros = SimpleUploadedFile('gros.jpg', b'\xff\xd8\xff' + b'0' * (6 * 1024 * 1024), content_type='image/jpeg')
        r = self.client.post('/api/profil/photo/', {'photo': gros})
        self.assertEqual(r.status_code, 400)

    def test_upload_non_connecte_interdit(self):
        self.client.logout()
        r = self.client.post('/api/profil/photo/', {'photo': _image_jpeg()})
        self.assertEqual(r.status_code, 302)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class OnboardingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('newpionnier', password='testpass123', first_name='Alice')
        self.client.login(username='newpionnier', password='testpass123')

    def test_onboarding_accessible(self):
        r = self.client.get('/onboarding/')
        self.assertEqual(r.status_code, 200)

    def test_premiere_question_sur_profil_vide(self):
        r = self.client.get('/onboarding/')
        self.assertContains(r, 'nom')

    def test_repondre_avance_la_progression(self):
        from profiles.models import UserProfile
        self.client.post('/onboarding/', {'etape': '1', 'nom_artiste': 'Alice la musicienne'})
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.assertEqual(profile.nom_artiste, 'Alice la musicienne')
        self.assertGreaterEqual(profile.onboarding_etape, 1)

    def test_profil_completion_calcule_correctement(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.assertEqual(profile.pourcentage_profil(), 0)
        profile.nom_artiste = 'Alice'
        profile.village = 'Sainte-Émélie'
        profile.save()
        self.assertEqual(profile.pourcentage_profil(), 25)

    def test_completion_100_avec_tous_les_champs(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.nom_artiste = 'Alice'
        profile.village = 'Montréal'
        profile.bio_courte = 'Musicienne'
        profile.passions = 'Musique et forêt'
        profile.experience = '10 ans de scène'
        profile.relations_cherchees = 'Collaborateurs'
        profile.offre_culturelle = 'Concerts et ateliers'
        profile.photo = _image_jpeg()
        profile.save()
        self.assertEqual(profile.pourcentage_profil(), 100)

    def test_onboarding_non_connecte_interdit(self):
        self.client.logout()
        r = self.client.get('/onboarding/')
        self.assertEqual(r.status_code, 302)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class ProfilPublicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('yonathan', password='testpass123', first_name='Yonathan')
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.nom_artiste = 'Yonathan'
        profile.village = "Sainte-Émélie-de-l'Énergie"
        profile.offre_culturelle = 'Musicien, animateur et bâtisseur de communauté'
        profile.bio_courte = 'Artiste et entrepreneur néovillageois'
        profile.onboarding_etape = 8
        profile.save()

    def test_page_publique_accessible_sans_connexion(self):
        self.client.logout()
        r = self.client.get('/p/yonathan/')
        self.assertEqual(r.status_code, 200)

    def test_page_affiche_nom_artiste(self):
        self.client.logout()
        r = self.client.get('/p/yonathan/')
        self.assertContains(r, 'Yonathan')

    def test_page_affiche_village(self):
        self.client.logout()
        r = self.client.get('/p/yonathan/')
        self.assertContains(r, 'Sainte-Émélie')

    def test_page_affiche_offre_culturelle(self):
        self.client.logout()
        r = self.client.get('/p/yonathan/')
        self.assertContains(r, 'Musicien')

    def test_username_inexistant_retourne_404(self):
        r = self.client.get('/p/utilisateur-qui-nexiste-pas/')
        self.assertEqual(r.status_code, 404)

    def test_page_ne_montre_pas_email(self):
        self.user.email = 'yonathan@secret.com'
        self.user.save()
        self.client.logout()
        r = self.client.get('/p/yonathan/')
        self.assertNotContains(r, 'yonathan@secret.com')


class VouteExterneTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('steve', password='testpass123')
        self.client.login(username='steve', password='testpass123')

    def test_profil_a_champ_nc_externe_url(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.nc_externe_url = 'https://cloud.entretablees.ca'
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.nc_externe_url, 'https://cloud.entretablees.ca')

    def test_profil_a_champ_nc_externe_token(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.nc_externe_token = 'mon-token-secret'
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.nc_externe_token, 'mon-token-secret')

    def test_profil_a_champ_saboteur(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.saboteur = 'Je procrastine quand...'
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.saboteur, 'Je procrastine quand...')

    def test_reglages_ma_voute_enregistre_token(self):
        r = self.client.post('/reglages/?section=ma_voute', {
            'section': 'ma_voute',
            'nc_externe_url': 'https://cloud.entretablees.ca',
            'nc_externe_token': 'mon-token-test',
        })
        self.assertRedirects(r, '/reglages/?section=ma_voute')
        from profiles.models import UserProfile
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.nc_externe_url, 'https://cloud.entretablees.ca')
        self.assertEqual(profile.nc_externe_token, 'mon-token-test')

    def test_reglages_ma_voute_accessible(self):
        r = self.client.get('/reglages/?section=ma_voute')
        self.assertEqual(r.status_code, 200)

    def test_saboteur_non_visible_sur_profil_public(self):
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.saboteur = 'Mon saboteur secret intime'
        profile.save()
        self.client.logout()
        r = self.client.get('/p/steve/')
        self.assertNotContains(r, 'Mon saboteur secret intime')


class VouteAdapterTest(TestCase):
    def test_adapter_local_pas_externe(self):
        from config.nextcloud import VouteAdapter
        user = User.objects.create_user('pionnier_local', password='test')
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.nc_username = 'pionnier_local'
        profile.nc_externe_url = ''
        profile.nc_externe_token = ''
        profile.save()
        adapter = VouteAdapter(profile)
        self.assertFalse(adapter.est_externe)
        self.assertEqual(adapter.nc_username, 'pionnier_local')

    def test_adapter_externe_detecte_token(self):
        from config.nextcloud import VouteAdapter
        user = User.objects.create_user('steve_ext', password='test')
        from profiles.models import UserProfile
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.nc_username = 'steve'
        profile.nc_externe_url = 'https://cloud.entretablees.ca'
        profile.nc_externe_token = 'token-steve'
        profile.save()
        adapter = VouteAdapter(profile)
        self.assertTrue(adapter.est_externe)
        self.assertEqual(adapter.base_url, 'https://cloud.entretablees.ca')
