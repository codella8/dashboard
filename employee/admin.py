from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count
from .models import Department, Employee, SalaryPayment, EmployeeExpense


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'employee_count', 'created_at']
    search_fields = ['name']
    list_per_page = 20
    
    def employee_count(self, obj):
        return obj.employee_set.filter(is_active=True).count()
    employee_count.short_description = 'Active Employees'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'employee_name', 'department', 'position', 'employment_type', 
        'salary_due', 'status_badge', 'hire_date'
    ]
    
    list_filter = ['department', 'employment_type', 'is_active', 'hire_date']
    search_fields = [
        'employee__user__first_name', 
        'employee__user__last_name', 
        'position'
    ]
    
    readonly_fields = ['created_at', 'financial_summary']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('employee', 'department', 'position', 'employment_type')
        }),
        ('Employment Details', {
            'fields': ('is_active', 'date', 'hire_date', 'termination_date')
        }),
        ('Financial Information', {
            'fields': ('salary_due', 'debt_to_company')
        }),
        ('Financial Summary', {
            'fields': ('financial_summary',),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('note', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def employee_name(self, obj):
        if obj.employee and obj.employee.user:
            return f"{obj.employee.user.get_full_name()}"
        return "No Employee"
    employee_name.short_description = 'Employee Name'

    def status_badge(self, obj):
        if obj.is_active:
            return format_html('<span class="badge badge-success">Active</span>')
        return format_html('<span class="badge badge-danger">Inactive</span>')
    status_badge.short_description = 'Status'

    def financial_summary(self, obj):
        total_paid = obj.salary_payments.filter(is_paid=True).aggregate(
            total=Sum('salary_amount')
        )['total'] or 0
        
        total_expenses = obj.expenses.aggregate(
            total=Sum('price')
        )['total'] or 0
        
        net_balance = obj.salary_due - total_paid - total_expenses - obj.debt_to_company
        
        return format_html("""
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff;">
                <h6 style="margin-top: 0; color: #007bff;">Financial Summary</h6>
                <div class="row">
                    <div class="col-md-6">
                        <strong>Salary Due:</strong> ${:,.2f}<br>
                        <strong>Total Paid:</strong> ${:,.2f}<br>
                        <strong>Total Expenses:</strong> ${:,.2f}
                    </div>
                    <div class="col-md-6">
                        <strong>Debt to Company:</strong> ${:,.2f}<br>
                        <strong>Net Balance:</strong> <span style="color: {}">${:,.2f}</span><br>
                        <strong>Payment Status:</strong> {}
                    </div>
                </div>
            </div>
        """, obj.salary_due, total_paid, total_expenses, obj.debt_to_company,
             '#28a745' if net_balance >= 0 else '#dc3545', net_balance,
             'Fully Paid' if net_balance <= 0 else 'Pending')
    financial_summary.short_description = 'Financial Summary'


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'employee_name', 'date', 'salary_amount', 'payment_method', 
        'payment_status', 'reference_number'
    ]
    
    list_filter = ['date', 'is_paid', 'payment_method']
    search_fields = [
        'employee__employee__user__first_name',
        'employee__employee__user__last_name',
        'reference_number'
    ]
    
    readonly_fields = ['created_at', 'payment_details']
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('employee', 'date', 'salary_amount', 'is_paid')
        }),
        ('Payment Method', {
            'fields': ('payment_method', 'reference_number')
        }),
        ('Payment Details', {
            'fields': ('payment_details',),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('note', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def employee_name(self, obj):
        return str(obj.employee)
    employee_name.short_description = 'Employee'

    def payment_status(self, obj):
        if obj.is_paid:
            return format_html('<span class="badge badge-success">Paid</span>')
        return format_html('<span class="badge badge-warning">Pending</span>')
    payment_status.short_description = 'Status'

    def payment_details(self, obj):
        return format_html("""
            <div style="background: #e8f5e8; padding: 15px; border-radius: 5px;">
                <strong>Payment Details:</strong><br>
                Employee: {}<br>
                Amount: ${:,.2f}<br>
                Date: {}<br>
                Method: {}<br>
                Reference: {}
            </div>
        """, obj.employee, obj.salary_amount, obj.date, 
             obj.get_payment_method_display(), obj.reference_number or 'N/A')
    payment_details.short_description = 'Payment Details'

    actions = ['mark_as_paid', 'mark_as_unpaid']

    def mark_as_paid(self, request, queryset):
        updated = queryset.update(is_paid=True)
        self.message_user(request, f'{updated} salary payments marked as paid.')
    mark_as_paid.short_description = "Mark selected as paid"

    def mark_as_unpaid(self, request, queryset):
        updated = queryset.update(is_paid=False)
        self.message_user(request, f'{updated} salary payments marked as unpaid.')
    mark_as_unpaid.short_description = "Mark selected as unpaid"


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