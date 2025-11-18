# accounts/views/profile_views.py
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction

from .models import UserProfile
from .forms import AddUserProfileForm


class OwnerOrStaffMixin(UserPassesTestMixin):
    """
    Allow access if the current user is staff/superuser or the owner of the profile.
    Use this mixin on Detail/Update/Delete views for protects.
    """
    def test_func(self):
        profile = getattr(self, "object", None)
        # If object is not yet set (e.g., CreateView), allow only logged-in staff to create for others
        if profile is None:
            return self.request.user.is_authenticated and (self.request.user.is_staff or self.request.user.is_superuser)
        # owner:
        try:
            return (profile.user == self.request.user) or self.request.user.is_staff or self.request.user.is_superuser
        except Exception:
            return self.request.user.is_staff or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, "Access denied.")
        return redirect(reverse_lazy("accounts:profile_list"))


class ProfileListView(LoginRequiredMixin, ListView):
    """
    List all profiles. If you want to restrict to only company members, override get_queryset.
    """
    model = UserProfile
    template_name = "accounts/profile_list.html"
    context_object_name = "profiles"
    paginate_by = 25
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("user", "company")
        # Optionally restrict to same company for non-staff:
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            # show only profiles that belong to the same company as current user's profile (if exists)
            try:
                user_profile = self.request.user.profile
                if user_profile.company:
                    qs = qs.filter(company=user_profile.company)
                else:
                    qs = qs.filter(user=self.request.user)
            except Exception:
                qs = qs.filter(user=self.request.user)
        return qs


class ProfileDetailView(LoginRequiredMixin, OwnerOrStaffMixin, DetailView):
    model = UserProfile
    template_name = "accounts/profile_detail.html"
    context_object_name = "profile"


class ProfileCreateView(LoginRequiredMixin, CreateView):
    """
    Create a UserProfile for the current user. Admin/staff can create for others (by selecting company/user in form).
    """
    model = UserProfile
    form_class = AddUserProfileForm
    template_name = "accounts/profile_add.html"
    success_url = reverse_lazy("accounts:profile_list")

    def form_valid(self, form):
        # If normal user is creating, bind to current user
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            form.instance.user = self.request.user
        # Use transaction to ensure data integrity
        with transaction.atomic():
            response = super().form_valid(form)
        messages.success(self.request, "Profile created successfully.")
        return response


class ProfileUpdateView(LoginRequiredMixin, OwnerOrStaffMixin, UpdateView):
    model = UserProfile
    form_class = AddUserProfileForm
    template_name = "accounts/profile_edit.html"
    success_url = reverse_lazy("accounts:profile_list")

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
        messages.success(self.request, "Profile updated successfully.")
        return response


class ProfileDeleteView(LoginRequiredMixin, OwnerOrStaffMixin, DeleteView):
    model = UserProfile
    template_name = "accounts/profile_confirm_delete.html"
    success_url = reverse_lazy("accounts:profile_list")

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        # Prevent users removing other's profiles unless staff
        if obj.user != request.user and not request.user.is_staff:
            messages.error(request, "You do not have permission to delete this profile.")
            return redirect(self.success_url)
        messages.success(request, "Profile deleted.")
        return super().delete(request, *args, **kwargs)
