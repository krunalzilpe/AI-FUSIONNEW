from django.db import migrations


def preserve_status(apps, schema_editor):
    Document = apps.get_model("assistant_app", "Document")
    Document.objects.filter(workspace_key="", processed=True).update(status="ready", progress=100)
    Document.objects.filter(workspace_key="", processed=False).update(status="failed", error="Legacy document needs reindexing.")


class Migration(migrations.Migration):
    dependencies = [("assistant_app", "0003_conversation_chatmessage_query_metadata_and_more")]
    operations = [migrations.RunPython(preserve_status, migrations.RunPython.noop)]
