from django.shortcuts import render

def home_expenses(request):
    return render(request, 'home_expenses.html')