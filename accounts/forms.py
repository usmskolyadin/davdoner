from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label='Имя', max_length=60)
    phone = forms.CharField(label='Телефон', max_length=32)

    class Meta:
        model = User
        fields = ('first_name', 'username', 'phone', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.profile.phone = self.cleaned_data['phone']
            user.profile.save()
        return user
