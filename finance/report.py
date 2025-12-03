# financial/report.py
from decimal import Decimal
from django.db.models import Sum, F, Value, Case, When, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import date, timedelta

from .models import CashTransaction, Account, Category

DEC_ZERO = Decimal("0.00")

def _as_decimal(v):
    return v if v is not None else DEC_ZERO

# -------------------------
# Basic helpers
# -------------------------
def cashflow_summary(start_date=None, end_date=None, account_id=None, currency=None):
    """
    Returns dict:
      { 'total_in': Decimal, 'total_out': Decimal, 'net': Decimal, 'by_account': [...], 'by_category': [...] }
    """
    if end_date is None:
        end_date = timezone.now().date()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    qs = CashTransaction.objects.filter(date__range=(start_date, end_date))
    if account_id:
        qs = qs.filter(account_id=account_id)
    if currency:
        qs = qs.filter(currency=currency)

    agg_in = qs.filter(direction="in").aggregate(total_in=Coalesce(Sum("amount"), Value(DEC_ZERO, output_field=DecimalField())))
    agg_out = qs.filter(direction="out").aggregate(total_out=Coalesce(Sum("amount"), Value(DEC_ZERO, output_field=DecimalField())))

    total_in = _as_decimal(agg_in["total_in"])
    total_out = _as_decimal(agg_out["total_out"])
    net = total_in - total_out

    # breakdown by account
    by_account_qs = qs.values("account__id", "account__name").annotate(
        total_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
        total_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
    ).order_by("-total_in", "-total_out")

    by_account = [
        {"account_id": r["account__id"], "account": r["account__name"], "total_in": r["total_in"], "total_out": r["total_out"]}
        for r in by_account_qs
    ]

    # breakdown by category
    by_cat_qs = qs.values("category__id", "category__name").annotate(
        total_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
        total_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
    ).order_by("-total_in", "-total_out")

    by_category = [
        {"category_id": r["category__id"], "category": r["category__name"], "total_in": r["total_in"], "total_out": r["total_out"]}
        for r in by_cat_qs
    ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_in": total_in,
        "total_out": total_out,
        "net": net,
        "by_account": by_account,
        "by_category": by_category,
    }

# -------------------------
# Time series (daily cashbook)
# -------------------------
def cash_timeseries(start_date, end_date=None, account_id=None, currency=None):
    """
    Returns list of { date: date, cash_in: Decimal, cash_out: Decimal, net: Decimal }
    """
    if end_date is None:
        end_date = timezone.now().date()
    qs = CashTransaction.objects.filter(date__range=(start_date, end_date))
    if account_id:
        qs = qs.filter(account_id=account_id)
    if currency:
        qs = qs.filter(currency=currency)

    series_qs = qs.values("date").annotate(
        cash_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
        cash_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
    ).order_by("date")

    series = []
    for r in series_qs:
        net = (r["cash_in"] or DEC_ZERO) - (r["cash_out"] or DEC_ZERO)
        series.append({"date": r["date"], "cash_in": r["cash_in"], "cash_out": r["cash_out"], "net": net})
    return series

# -------------------------
# Account statement
# -------------------------
def account_statement(account_id, start_date=None, end_date=None, currency=None):
    """
    Returns transaction list and opening/closing balances.
    Opening balance is computed as sum(in)-sum(out) before start_date.
    """
    if end_date is None:
        end_date = timezone.now().date()
    if start_date is None:
        # default: 30 days back
        start_date = end_date - timedelta(days=30)

    base_qs = CashTransaction.objects.filter(account_id=account_id)
    if currency:
        base_qs = base_qs.filter(currency=currency)

    opening_agg = base_qs.filter(date__lt=start_date).aggregate(
        opening_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
        opening_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
    )
    opening = _as_decimal(opening_agg["opening_in"]) - _as_decimal(opening_agg["opening_out"])

    txs = base_qs.filter(date__range=(start_date, end_date)).order_by("date", "created_at").values(
        "id", "date", "direction", "amount", "currency", "category__name", "reference", "note", "company__name", "profile__user__username"
    )

    # compute running balance on Python side (efficient enough for page-sized results)
    running = []
    bal = opening
    for t in txs:
        amt = Decimal(t["amount"]) if t["amount"] is not None else DEC_ZERO
        if t["direction"] == "in":
            bal += amt
        else:
            bal -= amt
        running.append({**t, "running_balance": bal})

    closing = bal
    return {"opening_balance": opening, "transactions": running, "closing_balance": closing, "start_date": start_date, "end_date": end_date}

# -------------------------
# Outstanding (payables/receivables)
# -------------------------
def outstanding_by_partner(partner_type="company", currency=None):
    """
    Sums outstanding amounts grouped by company or profile.
    partner_type: 'company' or 'profile'
    Logic: consider transactions linked to partner where direction indicates payment/receive.
    For a simple outstanding report we treat 'in' as company->received, 'out' as company->paid
    Outstanding = total_out_for_partner - total_in_for_partner  (if positive -> company is owed money? -- choose interpretation)
    We'll return both in/out and net.
    """
    qs = CashTransaction.objects.all()
    if currency:
        qs = qs.filter(currency=currency)

    if partner_type == "company":
        base = qs.filter(company__isnull=False).values("company__id", "company__name").annotate(
            total_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
            total_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
        ).order_by("-total_out")
        rows = [{"company_id": r["company__id"], "company": r["company__name"], "total_in": r["total_in"], "total_out": r["total_out"], "net": (r["total_in"] - r["total_out"])} for r in base]
        return rows

    else:  # profile
        base = qs.filter(profile__isnull=False).values("profile__id", "profile__user__username").annotate(
            total_in=Coalesce(Sum("amount", filter=Q(direction="in")), Value(DEC_ZERO), output_field=DecimalField()),
            total_out=Coalesce(Sum("amount", filter=Q(direction="out")), Value(DEC_ZERO), output_field=DecimalField())
        ).order_by("-total_out")
        rows = [{"profile_id": r["profile__id"], "profile": r["profile__user__username"], "total_in": r["total_in"], "total_out": r["total_out"], "net": (r["total_in"] - r["total_out"])} for r in base]
        return rows

# -------------------------
# Quick KPIs for dashboard
# -------------------------
def dashboard_kpis(days=7):
    end = timezone.now().date()
    start = end - timedelta(days=days - 1)
    summary = cashflow_summary(start_date=start, end_date=end)
    # highest inflow account
    top_account = summary["by_account"][0] if summary["by_account"] else None
    # usage
    return {
        "total_in": summary["total_in"],
        "total_out": summary["total_out"],
        "net": summary["net"],
        "top_account": top_account,
        "start_date": start,
        "end_date": end,
    }
