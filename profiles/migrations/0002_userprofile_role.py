from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[('member', 'Membre'), ('admin', 'Admin'), ('superadmin', 'Superadmin')],
                default='member',
                max_length=20,
            ),
        ),
    ]
