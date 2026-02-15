# expenses/views.py
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Expense, ExpenseCategory

def expense_list(request):
    # Get all expenses
    expenses = Expense.objects.select_related('category').all()
    
    # Get filter parameters
    search = request.GET.get('search', '')
    category_id = request.GET.get('category', '')
    
    # Apply filters
    if search:
        expenses = expenses.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(paid_to__icontains=search)
        )
    
    if category_id:
        expenses = expenses.filter(category_id=category_id)
    
    # Convert to list for amount filtering
    expense_list = list(expenses)

    # Calculate statistics
    total_amount = sum(e.total_amount for e in expense_list)
    total_count = len(expense_list)
    avg_amount = total_amount / total_count if total_count > 0 else 0
    
    # Category statistics
    categories = ExpenseCategory.objects.filter(is_active=True)
    category_stats = []
    for category in categories:
        cat_expenses = [e for e in expense_list if e.category_id == category.id]
        cat_total = sum(e.total_amount for e in cat_expenses)
        cat_count = len(cat_expenses)
        if cat_count > 0:
            category_stats.append({
                'name': category.name,
                'total': cat_total,
                'count': cat_count,
                'percentage': (cat_total / total_amount * 100) if total_amount > 0 else 0
            })
    
    # Sort by highest amount
    category_stats.sort(key=lambda x: x['total'], reverse=True)
    
    # Pagination
    paginator = Paginator(expense_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'expenses': page_obj,
        'page_obj': page_obj,
        'total_amount': total_amount,
        'total_count': total_count,
        'avg_amount': avg_amount,
        'category_stats': category_stats,
        'categories': categories,
        'page_title': 'Expense Management',
        'filters': {
            'search': search,
            'category': category_id,
        }
    }
    
    return render(request, 'expense/expense_list.html', context)


def expense_detail(request, pk):
    expense = get_object_or_404(Expense.objects.select_related('category'), pk=pk)
    
    # Similar expenses
    similar_expenses = Expense.objects.filter(
        category=expense.category
    ).exclude(
        id=expense.id
    ).select_related('category').order_by('-date')[:5]
    
    # Category statistics
    category_expenses = Expense.objects.filter(category=expense.category)
    category_total = sum(e.total_amount for e in category_expenses)
    category_count = category_expenses.count()
    
    if category_total > 0:
        percentage_of_category = (expense.total_amount / category_total) * 100
    else:
        percentage_of_category = 0
    
    context = {
        'expense': expense,
        'similar_expenses': similar_expenses,
        'category_total': category_total,
        'category_count': category_count,
        'percentage_of_category': round(percentage_of_category, 1),
        'page_title': f'Expense Details: {expense.title}',
    }
    
    return render(request, 'expense/expense_detail.html', context)