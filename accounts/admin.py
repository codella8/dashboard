# accounts/admin.py
import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from . import models
from .models import Company, UserProfile

User = get_user_model()
def export_as_csv(fields):
    """Reusable export action"""
    def export(modeladmin, queryset):
        model = modeladmin.model._meta
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename={model.model_name}.csv'
        writer = csv.writer(response)

        writer.writerow(fields)

        for obj in queryset:
            row = []
            for f in fields:
                value = obj
                for part in f.split("__"):
                    value = getattr(value, part, "")
                row.append(str(value))
            writer.writerow(row)

        return response

    export.short_description = "Export selected as CSV"
    return export

def verify_profiles(modeladmin, request, queryset):
    updated = queryset.update(is_verified=True)
    modeladmin.message_user(request, f"{updated} profiles marked as verified.")

verify_profiles.short_description = "Mark selected profiles as verified"


def deactivate_profiles(modeladmin, request, queryset):
    updated = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{updated} profiles deactivated.")

deactivate_profiles.short_description = "Deactivate selected profiles"

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name", "contact_person", "phone", "email", "is_active",
        "created_at", "total_employees",
    )
    search_fields = ("name", "contact_person", "phone", "email")
    list_filter = ("is_active",)
    readonly_fields = ("created_at", "updated_at", "total_employees")
    ordering = ("name",)
    list_per_page = 25

    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "contact_person", "phone", "email", "is_active")
        }),
        ("Address & Notes", {
            "fields": ("address", "note"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    actions = [
        export_as_csv([
            "id", "name", "contact_person", "phone", "email", "is_active"
        ])
    ]

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "short_name", "email", "phone",
        "role", "company_name", "is_verified", "is_active",
        "created_at",
    )
    search_fields = (
        "first_name", "last_name", "email",
        "phone", "company__name"
    )
    list_filter = ("role", "is_verified", "is_active", "company")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "company_name")
    list_per_page = 25

    fieldsets = (
        ("Personal Information", {
            "fields": (
                "user", "first_name", "last_name", "email", "phone",
                "date_of_birth", "national_id"
            )
        }),
        ("Address Information", {
            "fields": ("address", "state", "zipcode"),
            "classes": ("collapse",)
        }),
        ("System Information", {
            "fields": ("role", "company", "is_verified", "is_active")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "company_name"),
            "classes": ("collapse",)
        }),
    )

    actions = [
        verify_profiles,
        deactivate_profiles,
        export_as_csv([
            "id", "first_name", "last_name", "email",
            "phone", "role", "company_name", "is_verified"
        ])
    ]

@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name']