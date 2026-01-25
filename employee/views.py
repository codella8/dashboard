# employees/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q, Sum, Count, Avg, Max
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.contrib import messages
from reportlab.pdfgen import canvas
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from .models import Employee, SalaryPayment, EmployeeExpense
from accounts.models import UserProfile
from .forms import EmployeeForm,  SalaryPaymentForm
from .report import calculate_employee_financials
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from io import BytesIO

@login_required
@permission_required('employees.view_employee', raise_exception=True)
def employee_list(request):
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    employment_type = request.GET.get('type', 'all')
    sort_by = request.GET.get('sort', '-hire_date')
    page_number = request.GET.get('page', 1)
    employees = Employee.objects.filter(is_active=True).select_related(
        'employee__user', 
    ).order_by('-created_at') 
    if search_query:
        employees = employees.filter(
            Q(employee__user__first_name__icontains=search_query) |
            Q(employee__user__last_name__icontains=search_query) |
            Q(employee__user__email__icontains=search_query) |
            Q(position__icontains=search_query) |
            Q(employee__user__username__icontains=search_query)
        )
    if employment_type and employment_type != 'all':
        employees = employees.filter(employment_type=employment_type)
    if status_filter and status_filter != 'all':
        employees_with_financials = []
        for emp in employees:
            financials = calculate_employee_financials(emp)
            emp.financials = financials
            employees_with_financials.append(emp)
        if status_filter == 'paid':
            employees = [e for e in employees_with_financials if e.financials.get('is_fully_paid', False)]
        elif status_filter == 'partial':
            employees = [e for e in employees_with_financials 
                if not e.financials.get('is_fully_paid', False) 
                and e.financials.get('total_paid', 0) > 0]
        elif status_filter == 'unpaid':
            employees = [e for e in employees_with_financials 
                if e.financials.get('total_paid', 0) == 0]
    if sort_by == 'name':
        employees = sorted(employees, key=lambda x: x.employee.user.get_full_name() if x.employee and x.employee.user else '')
    elif sort_by == '-name':
        employees = sorted(employees, key=lambda x: x.employee.user.get_full_name() if x.employee and x.employee.user else '', reverse=True)
    elif sort_by == 'salary':
        employees = sorted(employees, key=lambda x: x.salary_due)
    elif sort_by == '-salary':
        employees = sorted(employees, key=lambda x: x.salary_due, reverse=True)
    elif sort_by == 'hire_date':
        employees = sorted(employees, key=lambda x: x.hire_date or datetime.max.date())
    elif sort_by == '-hire_date':
        employees = employees.order_by('-hire_date')
    else:
        employees = employees.order_by('-created_at')
    paginator = Paginator(employees, 25) 
    page_obj = paginator.get_page(page_number)
    employees_data = []
    for emp in page_obj:
        financials = calculate_employee_financials(emp)
        if financials.get('is_fully_paid', False):
            payment_status = {
                'label': 'Paid',
                'color': 'success',
                'icon': 'check-circle',
                'badge': 'badge bg-success'
            }
        elif financials.get('total_paid', 0) > 0:
            payment_status = {
                'label': 'Partial',
                'color': 'warning',
                'icon': 'exclamation-circle',
                'badge': 'badge bg-warning'
            }
        else:
            payment_status = {
                'label': 'Unpaid',
                'color': 'danger',
                'icon': 'times-circle',
                'badge': 'badge bg-danger'
            }
        payment_progress = financials.get('payment_percentage', 0)
        years_of_service = None
        if emp.hire_date:
            delta = timezone.now().date() - emp.hire_date
            years_of_service = delta.days / 365.25
        
        employees_data.append({
            'employee': emp,
            'financials': financials,
            'payment_status': payment_status,
            'payment_progress': payment_progress,
            'years_of_service': years_of_service,
            'has_advances': financials.get('total_advances', 0) > 0,
            'has_expenses': financials.get('total_expenses', 0) > 0,
        })
    total_stats = {
        'active_employees': Employee.objects.filter(is_active=True).count(),
        'total_salary': Employee.objects.filter(is_active=True).aggregate(
            total=Sum('salary_due')
        )['total'] or Decimal('0'),
        'total_paid': SalaryPayment.objects.filter(
            is_paid=True,
            employee__is_active=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0'),
        'avg_salary': Employee.objects.filter(is_active=True).aggregate(
            avg=Avg('salary_due')
        )['avg'] or Decimal('0'),
    }
    monthly_stats = []
    for i in range(5, -1, -1):
        month_date = timezone.now().date() - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        if i == 0:
            month_end = timezone.now().date()
        else:
            next_month = month_start.replace(day=28) + timedelta(days=4)
            month_end = next_month - timedelta(days=next_month.day)
        
        month_payments = SalaryPayment.objects.filter(
            date__range=[month_start, month_end],
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        month_employees = Employee.objects.filter(
            hire_date__lte=month_end,
            is_active=True
        ).count()
        
        monthly_stats.append({
            'month': month_start.strftime('%b %Y'),
            'total_payments': month_payments,
            'active_employees': month_employees,
            'month_start': month_start,
        })
    
    context = {
        'employees_data': employees_data,
        'page_obj': page_obj,
        'total_stats': total_stats,
        'monthly_stats': monthly_stats,
        'filters': {
            'search': search_query,
            'status': status_filter,
            'type': employment_type,
            'sort': sort_by,
        },
        'sort_options': [
            ('-created_at', 'Newest First'),
            ('created_at', 'Oldest First'),
            ('name', 'Name A-Z'),
            ('-name', 'Name Z-A'),
            ('salary', 'Salary Low-High'),
            ('-salary', 'Salary High-Low'),
            ('hire_date', 'Oldest Hires'),
            ('-hire_date', 'Newest Hires'),
        ],
        'status_options': [
            ('all', 'All Status'),
            ('paid', 'Paid'),
            ('partial', 'Partial'),
            ('unpaid', 'Unpaid'),
        ],
        'type_options': [
            ('all', 'All Types'),
            ('full_time', 'Full Time'),
            ('part_time', 'Part Time'),
            ('contract', 'Contract'),
            ('freelance', 'Freelance'),
        ],
    }
    
    return render(request, 'employee/employee_list.html', context)

@login_required
def employee_quick_view(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)   
    financials = calculate_employee_financials(employee)
    recent_payments = employee.salary_payments.filter(
        is_paid=True
    ).order_by('-date')[:5]
    recent_expenses = employee.expenses.all().order_by('-date')[:5]
    data = {
        'id': str(employee.id),
        'name': employee.employee.user.get_full_name() if employee.employee and employee.employee.user else 'Unknown',
        'position': employee.position or 'Not specified',
        'email': employee.employee.user.email if employee.employee and employee.employee.user else '',
        'phone': employee.employee.phone if employee.employee else '',
        'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '',
        'salary_due': str(employee.salary_due),
        'financials': {
            'total_paid': str(financials.get('total_paid', 0)),
            'total_expenses': str(financials.get('total_expenses', 0)),
            'remaining_balance': str(financials.get('remaining_balance', 0)),
            'payment_percentage': financials.get('payment_percentage', 0),
        },
        'recent_payments': [
            {
                'date': p.date.strftime('%Y-%m-%d'),
                'amount': str(p.salary_amount),
                'method': p.get_payment_method_display(),
            }
            for p in recent_payments
        ],
        'recent_expenses': [
            {
                'date': e.date.strftime('%Y-%m-%d'),
                'expense': e.expense,
                'amount': str(e.price),
                'category': e.get_category_display(),
            }
            for e in recent_expenses
        ],
        'status': 'paid' if financials.get('is_fully_paid', False) else 'partial' if financials.get('total_paid', 0) > 0 else 'unpaid',
    }
    
    return JsonResponse(data)

@login_required
def employee_bulk_actions(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        employee_ids = request.POST.getlist('employee_ids')
        if not employee_ids:
            messages.warning(request, 'No employees selected.')
            return redirect('employee:employee_list')       
        employees = Employee.objects.filter(id__in=employee_ids)
        if action == 'export_selected':
            messages.success(request, f'{employees.count()} employees exported successfully.')
        elif action == 'send_payment_reminders':
            messages.success(request, f'Payment reminders sent to {employees.count()} employees.')
        
        return redirect('employee:employee_list')
    
    return redirect('employee:employee_list')

@login_required
@permission_required('employees.view_employee', raise_exception=True)
def employee_detail(request, employee_id):
    employee = get_object_or_404(
        Employee.objects.select_related(
            'employee__user', 
        ).prefetch_related(
            'salary_payments',
            'expenses'
        ),
        id=employee_id,
        is_active=True
    )
    financials = calculate_employee_financials(employee)
    salary_payments = employee.salary_payments.all().order_by('-date')
    expenses = employee.expenses.all().order_by('-date')
    payment_stats = {
        'total_payments': salary_payments.count(),
        'paid_count': salary_payments.filter(is_paid=True).count(),
        'pending_count': salary_payments.filter(is_paid=False).count(),
        'total_paid_amount': salary_payments.filter(is_paid=True).aggregate(
            total=Sum('salary_amount')
        )['total'] or Decimal('0'),
        'avg_payment_amount': salary_payments.filter(is_paid=True).aggregate(
            avg=Avg('salary_amount')
        )['avg'] or Decimal('0'),
        'largest_payment': salary_payments.filter(is_paid=True).aggregate(
            max=Max('salary_amount')
        )['max'] or Decimal('0'),
        'last_payment_date': salary_payments.filter(is_paid=True).order_by('-date').first(),
    }
    expense_stats = {
        'total_expenses': expenses.count(),
        'total_amount': expenses.aggregate(total=Sum('price'))['total'] or Decimal('0'),
        'avg_expense': expenses.aggregate(avg=Avg('price'))['avg'] or Decimal('0'),
        'by_category': expenses.values('category').annotate(
            total=Sum('price'),
            count=Count('id')
        ).order_by('-total'),
    }
    years_of_service = None
    months_of_service = None
    if employee.hire_date:
        today = timezone.now().date()
        delta = today - employee.hire_date
        years_of_service = delta.days // 365
        months_of_service = (delta.days % 365) // 30
    if financials.get('is_fully_paid', False):
        payment_status = {
            'label': 'Paid in Full',
            'color': 'success',
            'icon': 'check-circle',
            'description': 'All payments completed'
        }
    elif financials.get('total_paid', 0) > 0:
        payment_status = {
            'label': 'Partial Payment',
            'color': 'warning',
            'icon': 'exclamation-circle',
            'description': f"{financials.get('payment_percentage', 0):.1f}% paid"
        }
    else:
        payment_status = {
            'label': 'No Payments',
            'color': 'danger',
            'icon': 'times-circle',
            'description': 'No payments received yet'
        }
    
    six_months_ago = timezone.now().date() - timedelta(days=180)
    recent_payments = salary_payments.filter(
        date__gte=six_months_ago
    ).order_by('-date')[:10]
    recent_expenses = expenses.filter(
        date__gte=six_months_ago
    ).order_by('-date')[:10]
    payment_trend_data = []
    for i in range(11, -1, -1):
        month_date = timezone.now().date() - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        if i == 0:
            month_end = timezone.now().date()
        else:
            next_month = month_start.replace(day=28) + timedelta(days=4)
            month_end = next_month - timedelta(days=next_month.day)
        
        month_payments = salary_payments.filter(
            date__range=[month_start, month_end],
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        payment_trend_data.append({
            'month': month_start.strftime('%b'),
            'year': month_start.strftime('%Y'),
            'full_month': month_start.strftime('%b %Y'),
            'amount': month_payments,
            'payment_count': salary_payments.filter(
                date__range=[month_start, month_end],
                is_paid=True
            ).count()
        })
    employee_info = {
        'full_name': employee.employee.user.get_full_name() if employee.employee and employee.employee.user else 'Unknown',
        'email': employee.employee.user.email if employee.employee and employee.employee.user else '',
        'position': employee.position or 'Not specified',
        'employment_type': employee.get_employment_type_display(),
        'hire_date': employee.hire_date,
        'years_of_service': years_of_service,
        'months_of_service': months_of_service,
        'status': 'Active' if employee.is_active else 'Inactive',
        'salary_due': employee.salary_due,
        'debt_to_company': employee.debt_to_company,
        'notes': employee.note,
    }
    
    context = {
        'employee': employee,
        'employee_info': employee_info,
        'financials': financials,
        'payment_status': payment_status,
        'salary_payments': salary_payments[:20],  
        'expenses': expenses[:20],  
        'payment_stats': payment_stats,
        'expense_stats': expense_stats,
        'recent_payments': recent_payments,
        'recent_expenses': recent_expenses,
        'payment_trend_data': payment_trend_data,
        'years_of_service': years_of_service,
        'today': timezone.now().date(),
    }
    
    return render(request, 'employees/employee_detail.html', context)


def calculate_employee_financials(employee):
    try:
        total_paid = employee.salary_payments.filter(
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        total_expenses = employee.expenses.aggregate(
            total=Sum('price')
        )['total'] or Decimal('0')
        debt_to_company = employee.debt_to_company or Decimal('0')
        net_salary = employee.salary_due - total_paid - total_expenses - debt_to_company
        payment_percentage = (total_paid / employee.salary_due * 100) if employee.salary_due > 0 else 0
        avg_monthly = employee.salary_payments.filter(
            is_paid=True
        ).aggregate(avg=Avg('salary_amount'))['avg'] or Decimal('0')
        last_payment = employee.salary_payments.filter(
            is_paid=True
        ).order_by('-date').first()
        recent_payments = employee.salary_payments.filter(
            is_paid=True,
            date__gte=timezone.now().date() - timedelta(days=90)
        ).order_by('date')
        
        payment_trend = 'stable'
        if recent_payments.count() >= 2:
            payments = list(recent_payments)
            if payments[-1].salary_amount > payments[0].salary_amount:
                payment_trend = 'up'
            elif payments[-1].salary_amount < payments[0].salary_amount:
                payment_trend = 'down'
        financial_health = 'good'
        if payment_percentage >= 90:
            financial_health = 'excellent'
        elif payment_percentage >= 70:
            financial_health = 'good'
        elif payment_percentage >= 50:
            financial_health = 'fair'
        else:
            financial_health = 'poor'
        
        return {
            'total_paid': total_paid,
            'total_expenses': total_expenses,
            'debt_to_company': debt_to_company,
            'net_salary': max(net_salary, Decimal('0')),
            'payment_percentage': round(payment_percentage, 1),
            'avg_monthly': avg_monthly,
            'last_payment': last_payment,
            'payment_trend': payment_trend,
            'financial_health': financial_health,
            'remaining_balance': max(net_salary, Decimal('0')),
            'is_fully_paid': net_salary <= 0,
            'days_since_last_payment': (
                (timezone.now().date() - last_payment.date).days 
                if last_payment else None
            )
        }
        
    except Exception as e:
        return {
            'total_paid': Decimal('0'),
            'total_expenses': Decimal('0'),
            'debt_to_company': Decimal('0'),
            'net_salary': employee.salary_due,
            'payment_percentage': 0,
            'avg_monthly': Decimal('0'),
            'last_payment': None,
            'payment_trend': 'stable',
            'financial_health': 'unknown',
            'remaining_balance': employee.salary_due,
            'is_fully_paid': False,
            'days_since_last_payment': None
        }

@login_required
@permission_required('employees.add_salarypayment', raise_exception=True)
def process_salary_payment(request):
    today = timezone.now().date()
    search_query = request.GET.get('search', '').strip()
    selected_employee_id = request.GET.get('employee', '')
    form = SalaryPaymentForm()
    selected_employee = None
    remaining_balance = Decimal('0')
    if selected_employee_id:
        try:
            selected_employee = Employee.objects.get(id=selected_employee_id, is_active=True)
            total_paid = selected_employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = selected_employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            remaining_balance = selected_employee.salary_due - total_paid - total_advances
            form = SalaryPaymentForm(initial={
                'employee': selected_employee,
                'date': today,
                'salary_amount': max(remaining_balance, Decimal('0')),
                'is_paid': True,
                'payment_method': 'bank_transfer',
            })
            
        except Employee.DoesNotExist:
            messages.error(request, 'Selected employee not found')
    if request.method == 'POST':
        form = SalaryPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.is_paid = True
            total_paid = payment.employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = payment.employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            max_payable = payment.employee.salary_due - total_paid - total_advances
            
            if payment.salary_amount > max_payable:
                messages.error(request, 
                    f'Amount exceeds maximum payable amount (${max_payable})')
            else:
                payment.save()
                employee_name = payment.employee.employee.user.get_full_name() if payment.employee.employee and payment.employee.employee.user else 'Unknown'
                messages.success(request, 
                    f'Payment of ${payment.salary_amount} processed for {employee_name}')
                return redirect('employee:payment_invoice', payment_id=payment.id)
        else:
            messages.error(request, 'Please check the form for errors')

    existing_employees = Employee.objects.filter(is_active=True).values_list('employee_id', flat=True)
    user_profiles = UserProfile.objects.filter(
        user__is_active=True,
        id__in=existing_employees
    ).select_related('user')
    if search_query:
        user_profiles = user_profiles.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
    employees_data = []
    for user_profile in user_profiles:
        try:
            emp = Employee.objects.get(
                employee=user_profile,
                is_active=True
            )
            total_paid = emp.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = emp.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            remaining = emp.salary_due - total_paid - total_advances
            if remaining <= 0:
                status = 'paid'
                status_label = 'Paid'
                status_color = 'success'
                status_icon = 'check-circle'
            elif remaining == emp.salary_due:
                status = 'unpaid'
                status_label = 'Unpaid'
                status_color = 'danger'
                status_icon = 'times-circle'
            else:
                status = 'partial'
                status_label = 'Partial'
                status_color = 'warning'
                status_icon = 'exclamation-circle'
            
            employees_data.append({
                'id': emp.id,
                'employee': emp,
                'user_profile': user_profile,
                'salary_due': emp.salary_due,
                'total_paid': total_paid,
                'total_advances': total_advances,
                'remaining': max(remaining, Decimal('0')),
                'status': status,
                'status_label': status_label,
                'status_color': status_color,
                'status_icon': status_icon,
                'department': emp.department.name if emp.department else 'No Department',
                'position': emp.position or 'Not specified',
                'is_selected': selected_employee_id == str(emp.id),
                'last_payment': emp.salary_payments.filter(
                    is_paid=True
                ).order_by('-date').first(),
            })
            
        except Employee.DoesNotExist:
            continue
    stats = {
        'total_employees': len(employees_data),
        'total_payable': sum([e['remaining'] for e in employees_data]),
        'paid_count': len([e for e in employees_data if e['status'] == 'paid']),
        'unpaid_count': len([e for e in employees_data if e['status'] == 'unpaid']),
        'partial_count': len([e for e in employees_data if e['status'] == 'partial']),
    }
    context = {
        'employees_data': employees_data,
        'form': form,
        'selected_employee': selected_employee,
        'remaining_balance': remaining_balance,
        'stats': stats,
        'today': today.strftime('%Y-%m-%d'),
        'filters': {
            'search': search_query,
            'employee': selected_employee_id,
        },
    }
    return render(request, 'employees/process_payment.html', context)

@login_required
def payment_invoice(request, payment_id):
    try:
        payment = get_object_or_404(
            SalaryPayment.objects.select_related(
                'employee__employee__user',
                'employee__department'
            ),
            id=payment_id
        )
        total_paid_until_now = payment.employee.salary_payments.filter(
            is_paid=True,
            date__lte=payment.date
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        total_advances = payment.employee.expenses.aggregate(
            total=Sum('price')
        )['total'] or Decimal('0')
        
        remaining_balance = payment.employee.salary_due - total_paid_until_now - total_advances
        
        context = {
            'payment': payment,
            'employee': payment.employee,
            'total_paid_until_now': total_paid_until_now,
            'total_advances': total_advances,
            'remaining_balance': remaining_balance,
            'company_name': 'Your Company Name',
            'company_address': '123 Business Street, City, Country',
            'company_phone': '+1 (123) 456-7890',
            'company_email': 'accounts@company.com',
            'invoice_date': timezone.now().date(),
            'invoice_number': f"INV-{payment.date.strftime('%Y%m')}-{str(payment.id)[:8]}",
        }
        
        return render(request, 'employees/payment_invoice.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading invoice: {str(e)}')
        return redirect('employee:process_salary_payment')


@login_required
def download_payment_pdf(request, payment_id):
    try:
        payment = get_object_or_404(
            SalaryPayment.objects.select_related(
                'employee__employee__user',
                'employee__department'
            ),
            id=payment_id
        )  
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        p.drawString(100, 800, f"Payment Invoice - {payment.employee.employee.user.get_full_name()}")
        p.drawString(100, 780, f"Payment Amount: ${payment.salary_amount}")
        p.drawString(100, 760, f"Payment Date: {payment.date}")
        p.drawString(100, 740, f"Payment Method: {payment.get_payment_method_display()}")
        
        if payment.reference_number:
            p.drawString(100, 720, f"Reference: {payment.reference_number}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        filename = f"payment_{payment.date.strftime('%Y%m%d')}_{payment.id[:8]}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating PDF: {str(e)}')
        return redirect('employee:payment_invoice', payment_id=payment_id)
    
@login_required
@permission_required('employees.add_salarypayment', raise_exception=True)
def process_salary_payment(request):
    today = timezone.now().date()
    search_query = request.GET.get('search', '').strip()
    selected_employee_id = request.GET.get('employee', '')
    form = SalaryPaymentForm()
    selected_employee = None
    remaining_balance = Decimal('0')
    if selected_employee_id:
        try:
            selected_employee = Employee.objects.get(id=selected_employee_id, is_active=True)
            total_paid = selected_employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = selected_employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            remaining_balance = selected_employee.salary_due - total_paid - total_advances
            form = SalaryPaymentForm(initial={
                'employee': selected_employee,
                'date': today,
                'salary_amount': max(remaining_balance, Decimal('0')),
                'is_paid': True,
            })
            
        except Employee.DoesNotExist:
            messages.error(request, 'Selected employee not found')
    if request.method == 'POST':
        form = SalaryPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.is_paid = True
            total_paid = payment.employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = payment.employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            max_payable = payment.employee.salary_due - total_paid - total_advances
            
            if payment.salary_amount > max_payable:
                messages.error(request, 
                    f'Amount exceeds maximum payable amount (${max_payable})')
            else:
                payment.save()
                return redirect('employee:payment_invoice', payment_id=payment.id)
        else:
            messages.error(request, 'Please check the form for errors')
def payroll_report(request):
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))
    report_start = datetime(year, month, 1).date()
    next_month = datetime(year + (month // 12), ((month % 12) + 1), 1).date()
    report_end = next_month - timedelta(days=1)
    salary_payments = SalaryPayment.objects.filter(date__gte=report_start, date__lte=report_end).select_related('employee', 'employee__employee', 'employee__employee__user').order_by('employee__employee__user__last_name')
    summary = salary_payments.aggregate(total_paid=Sum('salary_amount', filter=Q(is_paid=True)), total_pending=Sum('salary_amount', filter=Q(is_paid=False)), total_count=Count('id'), paid_count=Count('id', filter=Q(is_paid=True)), avg_amount=Avg('salary_amount'))
    employee_totals = {}
    for payment in salary_payments:
        eid = payment.employee.id
        if eid not in employee_totals:
            employee_totals[eid] = {'employee': payment.employee, 'total_paid': Decimal('0'), 'total_pending': Decimal('0'), 'payments': []}
        if payment.is_paid:
            employee_totals[eid]['total_paid'] += payment.salary_amount
        else:
            employee_totals[eid]['total_pending'] += payment.salary_amount
        employee_totals[eid]['payments'].append(payment)
    
    department_totals = {}
    for emp_data in employee_totals.values():
        dept_name = emp_data['employee'].department.name if emp_data['employee'].department else 'No Department'
        if dept_name not in department_totals:
            department_totals[dept_name] = {'total_paid': Decimal('0'), 'total_pending': Decimal('0'), 'employee_count': 0}
        department_totals[dept_name]['total_paid'] += emp_data['total_paid']
        department_totals[dept_name]['total_pending'] += emp_data['total_pending']
        department_totals[dept_name]['employee_count'] += 1

    return render(request, 'employee/payroll_report.html', {
        'salary_payments': salary_payments,
        'summary': summary,
        'employee_totals': employee_totals,
        'department_totals': department_totals,
        'report_start': report_start,
        'report_end': report_end,
        'selected_month': month,
        'selected_year': year,
        'months': range(1, 13),
        'years': range(timezone.now().year - 2, timezone.now().year + 1)
    })
    
def salary_payment(request):
    if request.method == "POST":
        form = SalaryPaymentForm(request.form)
        if form.is_valid():
            user = form.save()
            messages.success(request, ("payment form created successfully."))
            return redirect('employee:employee_detail')
        else:
            messages.error(request, ("Please correct the form errors"))
            
    else:
        form = SalaryPaymentForm()
    return render(request, 'employee:salary_payment', {'form': form})