from django.contrib import admin
from django.utils.html import format_html
from .models import Employee, EmployeeExpense

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'position', 'employment_type', 
        'salary_due', 'hire_date'
    ]
    
    list_filter = [ 'employment_type', 'is_active', 'hire_date']
    search_fields = [
        'employee__user__first_name', 
        'employee__user__last_name', 
        'position'
    ]
    
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('employee',  'position', 'employment_type')
        }),
        ('Employment Details', {
            'fields': ('is_active', 'date', 'hire_date', 'termination_date')
        }),
        ('Financial Information', {
            'fields': ('salary_due', 'debt_to_company')
        }),
        ('Additional Information', {
            'fields': ('note', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(EmployeeExpense)
class EmployeeExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'employee_name', 'date', 'expense', 'category_badge', 
        'price', 'formatted_date'
    ]
    
    list_filter = ['date', 'category']
    search_fields = [
        'employee__employee__user__first_name',
        'employee__employee__user__last_name',
        'expense'
    ]
    
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Expense Information', {
            'fields': ('employee', 'date', 'expense', 'category', 'price')
        }),
        ('Additional Information', {
            'fields': ('note', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def employee_name(self, obj):
        return str(obj.employee)
    employee_name.short_description = 'Employee'

    def category_badge(self, obj):
        colors = {
            'travel': 'primary',
            'equipment': 'info',
            'training': 'success',
            'bonus': 'warning',
            'overtime': 'danger',
            'other': 'secondary'
        }
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            colors.get(obj.category, 'secondary'), 
            obj.get_category_display()
        )
    category_badge.short_description = 'Category'

    def formatted_date(self, obj):
        return obj.date.strftime('%Y-%m-%d')
    formatted_date.short_description = 'Date'