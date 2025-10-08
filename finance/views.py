from django.shortcuts import render

def home_finance(request):
    return render(request, 'home_finance.html')
