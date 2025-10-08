from django.contrib import admin
from .models import Report, ReportEntry, ReportAttachment

class ReportEntryInline(admin.TabularInline):
    model = ReportEntry
    extra = 1
    fields = ['date', 'section', 'reference_id', 'description', 'amount']
    readonly_fields = []
    show_change_link = True

class ReportAttachmentInline(admin.TabularInline):
    model = ReportAttachment
    extra = 0
    fields = ['file', 'uploaded_at', 'note']
    readonly_fields = ['uploaded_at']
    show_change_link = True

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['title', 'report_type', 'created_by', 'created_at']
    list_filter = ['report_type', 'created_at']
    search_fields = ['title', 'note', 'created_by__username']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    inlines = [ReportEntryInline, ReportAttachmentInline]


@admin.register(ReportEntry)
class ReportEntryAdmin(admin.ModelAdmin):
    list_display = ['report', 'date', 'section', 'reference_id', 'amount']
    list_filter = ['section', 'date']
    search_fields = ['section', 'reference_id', 'description']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(ReportAttachment)
class ReportAttachmentAdmin(admin.ModelAdmin):
    list_display = ['report', 'file', 'uploaded_at']
    search_fields = ['note']
    readonly_fields = ['uploaded_at']
    ordering = ['-uploaded_at']

