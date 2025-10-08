from django.shortcuts import render

def home_inventory(request):
    return render(request, 'home_inventory.html')