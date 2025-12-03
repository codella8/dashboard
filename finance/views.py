# financial/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from .report import cashflow_summary, cash_timeseries, account_statement, outstanding_by_partner, dashboard_kpis
from .models import Account

@login_required
def cashflow_overview(request):
    """
    Page: cashflow overview for a date range (default 30 days).
    Template: financial/cashflow_overview.html
    """
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    # parse dates simply (expect YYYY-MM-DD)
    from datetime import datetime
    def _p(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except:
            return None
    start_date = _p(start)
    end_date = _p(end)
    summary = cashflow_summary(start_date=start_date, end_date=end_date)
    return render(request, "financial/cashflow_overview.html", {"summary": summary})

@login_required
def cashbook_timeseries(request):
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    from datetime import datetime
    def _p(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except:
            return None
    start_date = _p(start) or (timezone.now().date() - timezone.timedelta(days=30))
    end_date = _p(end) or timezone.now().date()
    series = cash_timeseries(start_date, end_date)
    return render(request, "financial/cashbook_timeseries.html", {"series": series, "start_date": start_date, "end_date": end_date})

@login_required
def account_statement_view(request, account_id):
    account = get_object_or_404(Account, id=account_id)
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    from datetime import datetime
    def _p(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except:
            return None
    start_date = _p(start)
    end_date = _p(end)
    stmt = account_statement(account.id, start_date=start_date, end_date=end_date)
    return render(request, "financial/account_statement.html", {"account": account, "stmt": stmt})

@login_required
def outstanding_view(request):
    partner = request.GET.get("partner", "company")  # company or profile
    rows = outstanding_by_partner(partner_type=partner)
    return render(request, "financial/outstanding.html", {"rows": rows, "partner": partner})

@login_required
def financial_dashboard(request):
    days = int(request.GET.get("days", 7))
    kpis = dashboard_kpis(days=days)
    accounts = Account.objects.filter(is_active=True)
    return render(request, "financial/dashboard.html", {"kpis": kpis, "accounts": accounts})
