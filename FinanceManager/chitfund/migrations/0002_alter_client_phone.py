from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chitfund", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="phone",
            field=models.CharField(max_length=15),
        ),
    ]
