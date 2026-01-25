from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, UserChangeForm, SetPasswordForm
from .models import UserProfile
from django import forms
from django.utils.translation import gettext_lazy as _


class UpdateUserInfo(forms.ModelForm):
    phone = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('phone')})
    )
    address1 = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('address1')}),
        required=False
    )
    address2 = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('address2')}),
        required=False
    )
    city = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('city')}),
        required=False
    )
    country = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('country')}),
        required=False
    )

    class Meta:
        model = UserProfile
        fields = ['phone', 'address1', 'address2', 'city', 'country']

class UpdatePasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(
        label="",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': _('Enter New Password:')
            }
        )
    )

    new_password2 = forms.CharField(
        label="",
        widget=forms.PasswordInput(
            attrs={
                'class': 'form-control',
                'placeholder': _('Enter Password Again:')
            }
        )
    )

class UserUpdateForm(UserChangeForm):
    password = None
    first_name = forms.CharField(
        label="",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Name')}),
        required=False
    )


    last_name = forms.CharField(
        label="",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('LastName')}),
        required=False
    )

    email = forms.EmailField(
        label="",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Email')}),
        required=False
    )

    username = forms.CharField(
        label="",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('UserName')}),
        required=False
    )
     

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'username')

class SignUpForm(UserCreationForm):
    first_name = forms.CharField(
        label="",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Name')})
    )

    last_name = forms.CharField(
        label="",
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('LastName')})
    )

    email = forms.EmailField(
        label="",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Email')})
    )

    username = forms.CharField(
        label="",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('UserName')})
    )

    password1 = forms.CharField(
        label="",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': _('Enter Your Password:')})
    )

    password2 = forms.CharField(
        label="",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': _('Enter Password Again:')})
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'password1', 'password2']