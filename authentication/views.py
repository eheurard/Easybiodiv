from django.contrib.auth import login
from django.shortcuts import render, redirect
from .forms import RegisterForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:index')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard:index')
    return render(request, 'authentication/register.html', {'form': form})
