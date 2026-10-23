from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label=_('Adresse email'))
    accept_terms = forms.BooleanField(
        required=True,
        label=_("J'accepte les conditions générales d'utilisation"),
        error_messages={
            'required': _("Vous devez accepter les conditions générales d'utilisation."),
        },
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = User.SUBSCRIBER
        user.terms_accepted_at = timezone.now()
        if commit:
            user.save()
        return user
