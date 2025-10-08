from django.shortcuts import render

# Create your views here.
def home_employee(request):
    return render(request, 'home_employee.html')