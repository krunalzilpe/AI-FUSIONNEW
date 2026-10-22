from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("file", models.FileField(upload_to="documents/")),
                ("file_type", models.CharField(max_length=10)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("page_count", models.PositiveIntegerField(default=0)),
                ("chunk_count", models.PositiveIntegerField(default=0)),
                ("processed", models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name="TextChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("page_number", models.PositiveIntegerField(default=1)),
                ("embedding", models.JSONField(default=list)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chunks",
                        to="assistant_app.document",
                    ),
                ),
            ],
            options={
                "ordering": ["document_id", "chunk_index"],
                "unique_together": {("document", "chunk_index")},
            },
        ),
    ]
