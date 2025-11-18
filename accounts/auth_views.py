# accounts/views/auth_views.py
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.contrib.auth import authenticate, login
from django.contrib.auth.views import LoginView, LogoutView
from django.views import View

from .forms import SignUpForm, AddUserProfileForm
from .models import UserProfile


class AppLoginView(LoginView):
    """
    Uses Django's built-in LoginView. Template should be accounts/login.html.
    """
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, "You have been logged in.")
        return super().form_valid(form)


class AppLogoutView(LogoutView):
    """
    Uses Django's built-in LogoutView.
    """
    next_page = reverse_lazy("accounts:login")  # change name as appropriate

    def dispatch(self, request, *args, **kwargs):
        messages.success(request, "You have been logged out.")
        return super().dispatch(request, *args, **kwargs)


class RegisterView(View):
    """
    Simple registration view that creates a User and a linked UserProfile.
    Uses SignUpForm (subclass of UserCreationForm) and optionally AddUserProfileForm data.
    The registration uses a DB transaction to ensure both User and UserProfile are created atomically.
    """
    template_name = "accounts/register.html"
    success_url = reverse_lazy("accounts:login")

    def get(self, request):
        signup_form = SignUpForm()
        profile_form = AddUserProfileForm(prefix="profile")
        return render(request, self.template_name, {"signup_form": signup_form, "profile_form": profile_form})

    def post(self, request):
        signup_form = SignUpForm(request.POST)
        profile_form = AddUserProfileForm(request.POST, prefix="profile")

        if signup_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user = signup_form.save(commit=False)
                # If your User model has is_active default False for email activation, adjust here
                user.is_active = True
                user.save()

                # create profile
                profile = profile_form.save(commit=False)
                profile.user = user
                # You can set defaults here, e.g. profile.account = UserProfile.ROLE_CUSTOMER
                profile.save()

            # authenticate and login immediately
            user = authenticate(request, username=signup_form.cleaned_data.get("username"),
                                password=signup_form.cleaned_data.get("password1"))
            if user:
                login(request, user)
                messages.success(request, "Registration successful. You are now logged in.")
                return redirect(reverse_lazy("accounts:profile_list"))
            else:
                messages.success(request, "Registration succeeded. Please login.")
                return redirect(self.success_url)

        # if invalid, fall through and re-render with errors
        return render(request, self.template_name, {"signup_form": signup_form, "profile_form": profile_form})
