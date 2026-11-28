from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0011_voute_externe_et_saboteur'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='photo_action',
            field=models.ImageField(blank=True, upload_to='photos/action/'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='casquettes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='specialites',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='engagements',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='liens',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
