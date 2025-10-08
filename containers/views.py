from django.shortcuts import render

def home_containers(request):
    return render(request, 'home_containers.html')