from functools import wraps
from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def creator_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{settings.LOGIN_URL}?next={request.path}')
        if request.user.role != 'CREATOR':
            return HttpResponseForbidden('Accès réservé aux créateurs.')
        return view_func(request, *args, **kwargs)
    return wrapper
