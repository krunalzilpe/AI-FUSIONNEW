from django.db import models


class Document(models.Model):
    workspace_key = models.CharField(max_length=80, blank=True, default="", db_index=True)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    file_type = models.CharField(max_length=10)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    processed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="queued")
    progress = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=400, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    index_signature = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [models.UniqueConstraint(
            fields=["workspace_key", "content_hash"],
            condition=~models.Q(content_hash=""), name="unique_workspace_content",
        )]


class Conversation(models.Model):
    workspace_key = models.CharField(max_length=80, db_index=True)
    title = models.CharField(max_length=100, default="New conversation")
    documents = models.ManyToManyField(Document, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class TextChunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    page_number = models.PositiveIntegerField(default=1)
    embedding = models.JSONField(default=list)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        unique_together = [("document", "chunk_index")]


class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, null=True, blank=True, on_delete=models.CASCADE, related_name="messages")
    question = models.TextField()
    answer = models.TextField()
    mode = models.CharField(max_length=30, default="gemini")
    sources_json = models.TextField(default="[]")
    created_at = models.DateTimeField(auto_now_add=True)
    query_metadata = models.JSONField(default=dict, blank=True)
    request_id = models.UUIDField(null=True, blank=True, unique=True)

    def __str__(self):
        return self.question[:80]

    class Meta:
        ordering = ["-created_at"]
