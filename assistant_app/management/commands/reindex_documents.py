from django.core.management.base import BaseCommand, CommandError
from assistant_app.models import Document
from assistant_app.rag import process_document


class Command(BaseCommand):
    help = "Rebuild selected document indexes with the configured embedding model. Also recovers interrupted local jobs."

    def add_arguments(self, parser):
        parser.add_argument("--document", type=int, action="append")
        parser.add_argument("--all", action="store_true")

    def handle(self, *args, **options):
        if not options["all"] and not options["document"]:
            raise CommandError("Choose --document ID (repeatable) or --all.")
        docs = Document.objects.all()
        if not options["all"]:
            docs = docs.filter(id__in=options["document"])
        failures = 0
        for doc in docs:
            doc.processed = False
            doc.save(update_fields=["processed"])
            try:
                count = process_document(doc)
                self.stdout.write(f"Document {doc.id}: indexed {count} chunks")
            except Exception:
                failures += 1
                self.stderr.write(f"Document {doc.id}: failed; inspect its processing status.")
        if failures:
            raise CommandError(f"{failures} document(s) failed.")
