from django.shortcuts import render

def home_crm(request):
    return render(request, 'crm/home_crm.html')
