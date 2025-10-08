from django.shortcuts import render


def home_reports(request):
    return render(request, 'home_reports.html')
