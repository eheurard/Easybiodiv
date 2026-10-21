from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label=_('Adresse email'))

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = User.SUBSCRIBER
        if commit:
            user.save()
        return user
