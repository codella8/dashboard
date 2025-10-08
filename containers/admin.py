from django.contrib import admin
from .models import Container

@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ['code', 'type', 'owner', 'capacity', 'is_active']
    list_filter = ['type', 'is_active']
    search_fields = ['code', 'note']
    ordering = ['code']
