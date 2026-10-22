from django.contrib import admin
from django.urls import path
from assistant_app import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload_document, name="upload_document"),
    path("ask/", views.ask_question, name="ask_question"),
    path("documents/", views.list_documents, name="list_documents"),
    path("document/<int:document_id>/delete/", views.delete_document, name="delete_document"),
    path("document/<int:document_id>/summary/", views.document_summary, name="document_summary"),
    path("document/<int:document_id>/questions/", views.document_questions, name="document_questions"),
    path("document/<int:document_id>/source/", views.document_source, name="document_source"),
    path("document/<int:document_id>/reindex/", views.reindex_document, name="reindex_document"),
    path("conversations/", views.conversations, name="conversations"),
    path("conversation/<int:conversation_id>/", views.conversation_detail, name="conversation_detail"),
    path("conversation/<int:conversation_id>/<str:action>/", views.conversation_action, name="conversation_action"),
    path("profile/", views.profile, name="profile"),
    path("api/stats/", views.system_stats, name="system_stats"),
    path("history/clear/", views.clear_history, name="clear_history"),
    path("health/", views.health, name="health"),
]

from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

