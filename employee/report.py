# employees/report.py - Enhanced with Intelligent Analysis
from django.db.models import Sum, Count, Avg, Max, Min, StdDev, Q, F
from django.db.models.functions import ExtractMonth, ExtractYear
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Employee, SalaryPayment, EmployeeExpense

def calculate_employee_financials(employee):
    total_paid = employee.salary_payments.filter(is_paid=True).aggregate(
        total=Sum('salary_amount')
    )['total'] or Decimal('0')
    
    total_expenses = employee.expenses.aggregate(
        total=Sum('price')
    )['total'] or Decimal('0')
    last_3_payments = employee.salary_payments.filter(
        is_paid=True
    ).order_by('-date')[:3]
    
    avg_last_3 = sum(p.salary_amount for p in last_3_payments) / len(last_3_payments) if last_3_payments else Decimal('0')
    growth_rate = Decimal('0')
    if len(last_3_payments) >= 2:
        old_avg = sum(p.salary_amount for p in last_3_payments[1:]) / 2
        if old_avg > 0:
            growth_rate = ((last_3_payments[0].salary_amount - old_avg) / old_avg * 100)
    
    net_balance = employee.salary_due - total_paid - total_expenses - employee.debt_to_company
    
    return {
        'total_paid': total_paid,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'is_fully_paid': net_balance <= 0,
        'remaining_balance': max(net_balance, Decimal('0')),
        'avg_last_3_payments': avg_last_3,
        'salary_growth_rate': growth_rate,
        'payment_count': employee.salary_payments.filter(is_paid=True).count(),
        'expense_count': employee.expenses.count(),
        'efficiency_score': (total_paid / employee.salary_due * 100) if employee.salary_due > 0 else 0,
        'financial_health': 'Excellent' if net_balance <= 0 and growth_rate <= 20 else                       
        'Good' if net_balance <= employee.salary_due * Decimal('0.2') else
                           
                           
        'Warning' if net_balance <= employee.salary_due * Decimal('0.5') else 'Critical'
    }


def get_payroll_summary(start_date=None, end_date=None):
    qs = SalaryPayment.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    summary = qs.aggregate(
        total_paid=Sum('salary_amount', filter=Q(is_paid=True)),
        total_pending=Sum('salary_amount', filter=Q(is_paid=False)),
        payment_count=Count('id'),
        paid_count=Count('id', filter=Q(is_paid=True)),
        pending_count=Count('id', filter=Q(is_paid=False)),
        avg_salary=Avg('salary_amount'),
        max_salary=Max('salary_amount'),
        min_salary=Min('salary_amount'),
        salary_stddev=StdDev('salary_amount')
    )
    payment_distribution = qs.values('payment_method').annotate(
        total_amount=Sum('salary_amount'),
        count=Count('id'),
        percentage=Count('id') * 100.0 / summary['payment_count'] if summary['payment_count'] else 0
    ).order_by('-total_amount')
    monthly_trend = qs.filter(is_paid=True).annotate(
        year=ExtractYear('date'),
        month=ExtractMonth('date')
    ).values('year', 'month').annotate(
        monthly_total=Sum('salary_amount'),
        payment_count=Count('id'),
        avg_per_payment=Avg('salary_amount')
    ).order_by('-year', '-month')[:6]
    predicted_next = Decimal('0')
    if monthly_trend and len(monthly_trend) >= 2:
        recent_months = list(monthly_trend)[:3]
        avg_recent = sum(item['monthly_total'] for item in recent_months) / len(recent_months)
        predicted_next = avg_recent * Decimal('1.05')
    dept_payroll = SalaryPayment.objects.filter(
        is_paid=True,
        date__range=[start_date, end_date] if start_date and end_date else Q()
    ).values(
        'employee__department__name'
    ).annotate(
        dept_total=Sum('salary_amount'),
        dept_count=Count('id'),
        dept_avg=Avg('salary_amount')
    ).order_by('-dept_total')
    
    return {
        'summary': summary,
        'payment_distribution': payment_distribution,
        'monthly_trend': monthly_trend,
        'predicted_next_month': predicted_next,
        'department_analysis': dept_payroll,
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'key_metrics': {
            'payment_efficiency': (summary['paid_count'] / summary['payment_count'] * 100) if summary['payment_count'] else 0,
            'salary_variability': summary['salary_stddev'] or Decimal('0'),
            'pending_ratio': (summary['pending_count'] / summary['payment_count'] * 100) if summary['payment_count'] else 0
        }
    }

def get_employee_performance(start_date=None, end_date=None):
    employees = Employee.objects.filter(is_active=True).select_related(
        'employee', 'employee__user', 'department'
    )
    performance_data = []    
    for employee in employees:
        financials = calculate_employee_financials(employee)
        payments_in_period = employee.salary_payments.all()
        expenses_in_period = employee.expenses.all()
        if start_date:
            payments_in_period = payments_in_period.filter(date__gte=start_date)
            expenses_in_period = expenses_in_period.filter(date__gte=start_date)
        if end_date:
            payments_in_period = payments_in_period.filter(date__lte=end_date)
            expenses_in_period = expenses_in_period.filter(date__lte=end_date)
        
        period_payments = payments_in_period.filter(is_paid=True).aggregate(
            total=Sum('salary_amount')
        )['total'] or Decimal('0')
        
        period_expenses = expenses_in_period.aggregate(
            total=Sum('price')
        )['total'] or Decimal('0')
        on_time_payments = payments_in_period.filter(
            is_paid=True,
            date__lte=F('employee__date')
        ).count()
        total_paid_count = payments_in_period.filter(is_paid=True).count()
        timeliness_score = (on_time_payments / total_paid_count * 100) if total_paid_count > 0 else 100
        expense_control_score = 100 - min(100, (period_expenses / employee.salary_due * 100) if employee.salary_due > 0 else 0)
        efficiency_score = (period_payments / employee.salary_due * 100) if employee.salary_due > 0 else 0
        overall_score = (
            efficiency_score * 0.4 +  
            timeliness_score * 0.3 +      
            expense_control_score * 0.2 +
            (financials['salary_growth_rate'] if financials['salary_growth_rate'] <= 30 else 30) * 0.1 
        )
        if overall_score >= 90:
            performance_level = 'Top Performer'
            badge_color = 'success'
            action = 'Consider promotion/bonus'
        elif overall_score >= 75:
            performance_level = 'High Performer'
            badge_color = 'info'
            action = 'Maintain and develop'
        elif overall_score >= 60:
            performance_level = 'Solid Performer'
            badge_color = 'warning'
            action = 'Provide coaching/training'
        else:
            performance_level = 'Development Needed'
            badge_color = 'danger'
            action = 'Performance improvement plan'
        
        performance_data.append({
            'employee': employee,
            'financials': financials,
            'period_payments': period_payments,
            'period_expenses': period_expenses,
            'efficiency_score': round(efficiency_score, 1),
            'timeliness_score': round(timeliness_score, 1),
            'expense_control_score': round(expense_control_score, 1),
            'overall_score': round(overall_score, 1),
            'performance_level': performance_level,
            'badge_color': badge_color,
            'years_of_service': (
                (timezone.now().date() - employee.hire_date).days / 365.25
                if employee.hire_date else 0
            ),
            'recommended_action': action,
            'risk_factors': [
                'High salary growth' if financials['salary_growth_rate'] > 30 else None,
                'Excessive expenses' if period_expenses > employee.salary_due * Decimal('0.3') else None,
                'Payment delays' if timeliness_score < 80 else None
            ]
        })
    
    return sorted(performance_data, key=lambda x: x['overall_score'], reverse=True)

def get_expense_analysis(start_date=None, end_date=None):
    qs = EmployeeExpense.objects.all()

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    total_expenses = qs.aggregate(
        total=Sum('price'),
        count=Count('id'),
        avg=Avg('price'),
        max=Max('price'),
        min=Min('price'),
        stddev=StdDev('price')
    )

    by_category = qs.values('category').annotate(
        total_amount=Sum('price'),
        expense_count=Count('id'),
        avg_amount=Avg('price'),
        percentage=Sum('price') * 100.0 / total_expenses['total'] if total_expenses['total'] else 0,
        max_in_category=Max('price')
    ).order_by('-total_amount')
    by_employee = qs.select_related(
        'employee', 'employee__employee', 'employee__employee__user'
    ).values(
        'employee_id',
        'employee__employee__user__first_name',
        'employee__employee__user__last_name',
        'employee__department__name'
    ).annotate(
        total_amount=Sum('price'),
        expense_count=Count('id'),
        avg_amount=Avg('price'),
        last_expense_date=Max('date')
    ).order_by('-total_amount')
    monthly_expenses = qs.annotate(
        year=ExtractYear('date'),
        month=ExtractMonth('date')
    ).values('year', 'month').annotate(
        total_amount=Sum('price'),
        expense_count=Count('id'),
        avg_per_expense=Avg('price')
    ).order_by('year', 'month')
    patterns = []
    if by_category:
        top_category = by_category[0]
        patterns.append({
            'type': 'Category Concentration',
            'detail': f"Top category '{top_category['category']}' accounts for {top_category['percentage']:.1f}% of expenses"
        })
    anomalies = []
    if total_expenses['avg'] and total_expenses['stddev']:
        anomaly_threshold = total_expenses['avg'] + (2 * total_expenses['stddev'])
        anomalous_expenses = qs.filter(price__gt=anomaly_threshold)
        if anomalous_expenses.exists():
            anomalies = list(anomalous_expenses.select_related(
                'employee', 'employee__employee__user'
            )[:10])
    growth_rate = Decimal('0')
    if len(monthly_expenses) >= 2:
        recent_months = list(monthly_expenses)[-2:]
        if recent_months[0]['total_amount'] and recent_months[0]['total_amount'] > 0:
            growth_rate = ((recent_months[1]['total_amount'] - recent_months[0]['total_amount']) / 
            recent_months[0]['total_amount'] * 100)
    expense_health = 'Healthy'
    if total_expenses['stddev'] and total_expenses['avg']:
        variability = (total_expenses['stddev'] / total_expenses['avg'] * 100)
        if variability > 100:
            expense_health = 'Volatile'
        elif len(anomalies) > 5:
            expense_health = 'Concerning'
    
    return {
        'summary': total_expenses,
        'by_category': by_category,
        'by_employee': by_employee[:15], 
        'monthly_expenses': monthly_expenses,
        'patterns': patterns,
        'anomalies': {
            'count': len(anomalies),
            'total_value': sum(a.price for a in anomalies) if anomalies else Decimal('0'),
            'items': anomalies[:5] 
        },
        'growth_rate': round(growth_rate, 1),
        'expense_health': expense_health,
        'recommendations': [
            'Review high-expense categories' if by_category and by_category[0]['percentage'] > 50 else None,
            'Investigate expense anomalies' if anomalies else None,
            'Monitor monthly growth' if abs(growth_rate) > 20 else None
        ]
    }
def get_salary_trends(group_by='month'):
    qs = SalaryPayment.objects.filter(is_paid=True)
    
    if group_by == 'month':
        trends = qs.annotate(
            year=ExtractYear('date'),
            month=ExtractMonth('date')
        ).values('year', 'month').annotate(
            total_paid=Sum('salary_amount'),
            payment_count=Count('id'),
            avg_salary=Avg('salary_amount'),
            max_salary=Max('salary_amount'),
            min_salary=Min('salary_amount'),
            salary_range=F('max_salary') - F('min_salary')
        ).order_by('year', 'month')
        enhanced_trends = []
        prev_total = None
        for trend in trends:
            month_change = None
            if prev_total is not None and prev_total > 0:
                month_change = ((trend['total_paid'] - prev_total) / prev_total * 100)
            
            enhanced_trends.append({
                **trend,
                'month_change': round(month_change, 1) if month_change is not None else None,
                'month_name': f"{trend['year']}-{trend['month']:02d}",
                'trend_direction': 'up' if month_change and month_change > 0 else 
                'down' if month_change and month_change < 0 else 'stable'
            })
            prev_total = trend['total_paid']
        predicted_next = None
        avg_growth = None
        if len(enhanced_trends) >= 3:
            last_3 = enhanced_trends[-3:]
            avg_growth = sum(t['month_change'] or 0 for t in last_3) / 3
            predicted_next = last_3[-1]['total_paid'] * (1 + avg_growth / 100)
        seasonal_pattern = 'No clear pattern'
        if len(enhanced_trends) >= 12:
            monthly_totals = {}
            for t in enhanced_trends:
                month = t['month']
                monthly_totals.setdefault(month, []).append(t['total_paid'])
            pattern_found = False
            for month, totals in monthly_totals.items():
                if len(totals) > 1 and max(totals) > min(totals) * 1.5:
                    pattern_found = True
                    break
            seasonal_pattern = 'Seasonal patterns detected' if pattern_found else 'No seasonal patterns'
        return {
            'trends': enhanced_trends,
            'predicted_next_month': predicted_next,
            'avg_monthly_growth': round(avg_growth, 1) if avg_growth else None,
            'total_period': sum(t['total_paid'] for t in enhanced_trends) if enhanced_trends else Decimal('0'),
            'seasonal_pattern': seasonal_pattern,
            'volatility': 'High' if enhanced_trends and max(t.get('month_change', 0) or 0 for t in enhanced_trends) > 30 else 
            'Medium' if enhanced_trends and max(t.get('month_change', 0) or 0 for t in enhanced_trends) > 15 else 'Low'
        }
    
    else: 
        daily_trends = qs.values('date').annotate(
            total_paid=Sum('salary_amount'),
            payment_count=Count('id'),
            avg_per_payment=Avg('salary_amount')
        ).order_by('date')
        busiest_day = max(daily_trends, key=lambda x: x['total_paid']) if daily_trends else None
        avg_daily = sum(t['total_paid'] for t in daily_trends) / len(daily_trends) if daily_trends else Decimal('0')
        
        return {
            'trends': daily_trends,
            'busiest_day': busiest_day,
            'avg_daily_payroll': avg_daily,
            'day_of_week_pattern': 'Weekend spike' if busiest_day and busiest_day['date'].weekday() >= 5 else 'Weekday pattern',
            'data_points': len(daily_trends)
        }


def get_employee_financial_status():
    employees = Employee.objects.filter(is_active=True).select_related(
        'employee', 'employee__user', 'department'
    )
    status_data = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        risk_score = 0
        risk_factors = []
        if financials['net_balance'] > employee.salary_due * Decimal('0.5'):
            risk_score += 30
            risk_factors.append('High outstanding balance')
        if financials['salary_growth_rate'] > 30:
            risk_score += 20
            risk_factors.append('Rapid salary growth')
        if financials['total_expenses'] > employee.salary_due * Decimal('0.4'):
            risk_score += 25
            risk_factors.append('High expense ratio')
        if employee.debt_to_company > employee.salary_due * Decimal('0.3'):
            risk_score += 25
            risk_factors.append('Significant company debt')
        if financials['payment_count'] < 3: 
            risk_score += 10
            risk_factors.append('Limited payment history')
        if risk_score >= 70:
            risk_level = 'High Risk'
            risk_color = 'danger'
            action_required = 'Immediate review needed'
        elif risk_score >= 40:
            risk_level = 'Medium Risk'
            risk_color = 'warning'
            action_required = 'Monitor closely'
        else:
            risk_level = 'Low Risk'
            risk_color = 'success'
            action_required = 'No action required'
        payment_progress = (financials['total_paid'] / employee.salary_due * 100) if employee.salary_due > 0 else 0
        
        status_data.append({
            'employee': employee,
            'salary_due': employee.salary_due,
            'total_paid': financials['total_paid'],
            'total_expenses': financials['total_expenses'],
            'debt_to_company': employee.debt_to_company,
            'net_balance': financials['net_balance'],
            'status': 'Paid in Full' if financials['is_fully_paid'] else 'Pending Payment',
            'payment_progress': round(payment_progress, 1),
            'risk_score': risk_score,
            'risk_level': risk_level,
            'risk_color': risk_color,
            'risk_factors': [f for f in risk_factors if f],
            'salary_growth': round(financials['salary_growth_rate'], 1),
            'efficiency': round(financials['efficiency_score'], 1),
            'financial_health': financials['financial_health'],
            'action_required': action_required,
            'recommendations': [
                'Accelerate payment collection' if risk_score >= 40 else None,
                'Review expense approvals' if 'High expense ratio' in risk_factors else None,
                'Schedule payment plan' if 'High outstanding balance' in risk_factors else None
            ]
        })
    return sorted(status_data, key=lambda x: (-x['risk_score'], -x['net_balance']))

def get_upcoming_salary_payments(days=30):
    today = timezone.now().date()
    future_date = today + timedelta(days=days)
    employees = Employee.objects.filter(
        is_active=True,
        salary_due__gt=0
    ).select_related('employee', 'employee__user', 'department')
    upcoming_payments = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        
        if financials['remaining_balance'] > 0:
            priority_score = 0
            due_date = employee.date or today + timedelta(days=30)
            days_until_due = (due_date - today).days
            
            if days_until_due <= 0:
                priority_score += 40 
                status = 'Overdue'
            elif days_until_due <= 7:
                priority_score += 30
                status = 'Due This Week'
            elif days_until_due <= 14:
                priority_score += 20
                status = 'Due Next Week'
            else:
                priority_score += 10
                status = 'Upcoming'
            if financials['remaining_balance'] > employee.salary_due * Decimal('0.5'):
                priority_score += 25
            if employee.hire_date:
                years_of_service = (today - employee.hire_date).days / 365.25
                if years_of_service > 5:
                    priority_score += 15 
                elif years_of_service > 2:
                    priority_score += 10
                else:
                    priority_score += 5
            if employee.department and employee.department.name in ['Sales', 'Engineering']:
                priority_score += 10
            if priority_score >= 60:
                priority_level = 'Critical'
                priority_color = 'danger'
                action = 'Process immediately'
            elif priority_score >= 40:
                priority_level = 'High'
                priority_color = 'warning'
                action = 'Process within 3 days'
            elif priority_score >= 20:
                priority_level = 'Medium'
                priority_color = 'info'
                action = 'Process within 7 days'
            else:
                priority_level = 'Low'
                priority_color = 'success'
                action = 'Process within 14 days'
            recommended_method = 'bank_transfer'
            if financials['remaining_balance'] < Decimal('1000'):
                recommended_method = 'digital'
            elif priority_score >= 40:
                recommended_method = 'cash'
            upcoming_payments.append({
                'employee': employee,
                'amount_due': financials['remaining_balance'],
                'due_date': due_date,
                'days_until_due': days_until_due,
                'status': status,
                'priority_score': priority_score,
                'priority_level': priority_level,
                'priority_color': priority_color,
                'recommended_action': action,
                'recommended_payment_method': recommended_method,
                'risk_indicators': [
                    'Overdue payment' if status == 'Overdue' else None,
                    'High amount relative to salary' if financials['remaining_balance'] > employee.salary_due * Decimal('0.7') else None,
                    'Multiple pending payments' if financials['payment_count'] > 1 and not financials['is_fully_paid'] else None
                ],
                'employee_value_score': (
                    (years_of_service * 10) + 
                    (1 if employee.employment_type == 'full_time' else 0.5) * 20 +
                    (financials['efficiency_score'] / 10)
                )
            })
    return sorted(upcoming_payments, key=lambda x: (-x['priority_score'], x['due_date']))