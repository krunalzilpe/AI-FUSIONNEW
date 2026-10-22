import uuid


def workspace_key(request):
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return f"user:{request.user.pk}"
    if "workspace_id" not in request.session:
        request.session["workspace_id"] = str(uuid.uuid4())
    return "guest:" + request.session["workspace_id"]
