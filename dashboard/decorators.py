from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.utils.translation import gettext as _


def creator_required_json(view):
    """Réserve une vue d'écriture JSON aux Créateurs (403 JSON sinon)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated or user.role != 'CREATOR':
            return JsonResponse(
                {'errors': {'__all__': [_('Accès réservé aux créateurs.')]}}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


def creator_required(view):
    """Réserve une vue HTML d'écriture aux Créateurs (login si anonyme, 403 sinon)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if user.role != 'CREATOR':
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper
