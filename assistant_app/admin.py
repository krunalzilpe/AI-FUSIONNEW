from django.contrib import admin
from .models import Document, TextChunk, ChatMessage


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "file_type", "page_count", "chunk_count", "processed", "uploaded_at"]
    list_filter = ["file_type", "processed"]
    search_fields = ["title"]
    readonly_fields = ["uploaded_at", "page_count", "chunk_count", "processed"]


@admin.register(TextChunk)
class TextChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "chunk_index", "page_number", "text_preview"]
    list_filter = ["document"]
    search_fields = ["text"]

    def text_preview(self, obj):
        return obj.text[:80] + "…" if len(obj.text) > 80 else obj.text
    text_preview.short_description = "Preview"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ["question_preview", "mode", "created_at"]
    list_filter = ["mode"]

    def question_preview(self, obj):
        return obj.question[:80]
    question_preview.short_description = "Question"
