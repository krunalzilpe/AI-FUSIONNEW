import json
import uuid
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from assistant_app.models import Document, ChatMessage, Conversation


class Command(BaseCommand):
    help = "Assign preserved pre-upgrade documents/history to a specific local workspace. Get its ID from Settings."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-key", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        key = options["workspace_key"]
        try:
            prefix, value = key.split(":", 1)
            if prefix == "guest":
                uuid.UUID(value)
            elif prefix != "user" or not value.isdecimal():
                raise ValueError
        except ValueError:
            raise CommandError("Use the workspace ID displayed in Settings.")
        count = Document.objects.filter(workspace_key="").update(workspace_key=key)
        turns = ChatMessage.objects.filter(conversation__isnull=True).order_by("created_at", "id")
        restored = 0
        for turn in turns:
            conversation = Conversation.objects.create(workspace_key=key, title=turn.question[:100])
            try:
                ids = [s["doc_id"] for s in json.loads(turn.sources_json)]
            except (ValueError, KeyError, TypeError):
                ids = []
            conversation.documents.set(Document.objects.filter(workspace_key=key, id__in=ids))
            turn.conversation = conversation
            turn.save(update_fields=["conversation"])
            restored += 1
        self.stdout.write(f"Adopted {count} documents and {restored} historical answers. Reindex documents before querying the new model.")
