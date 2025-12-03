# report.py
"""
Comprehensive reporting helpers for the whole system.

Usage:
    from .report import system_full_report, daily_summary, cashflow_summary

Place this file in a central app (e.g. `reports` or `daily_sale`) and import
functions in views or scheduled tasks.

Notes:
- Functions return plain Python dicts / lists (JSON-serializable-friendly).
- Safe: if a dependent app/model is missing the function returns None/empty.
- For heavy ranges, prefer pagination or background job (e.g. Celery). This module
  focuses on correctness and clear aggregation queries.
"""

from decimal import Decimal
from datetime import datetime, date, timedelta
import logging
from typing import Optional, Tuple, Dict, Any, List

from django.db.models import Sum, Count, Avg, F, Value, DecimalField
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncYear
from django.utils import timezone

logger = logging.getLogger(__name__)

DEC_ZERO = Decimal("0.00")


# --- Try to import app models; fall back gracefully if missing --- #
def _import_model(path: str):
    """
    Import a model by dotted path 'app.Model' and return the class or None.
    """
    try:
        app_label, model_name = path.split(".")
        from django.apps import apps
        return apps.get_model(app_label, model_name)
    except Exception as e:
        logger.debug("Model import failed for %s: %s", path, e)
        return None


DailySaleTransaction = _import_model("daily_sale.DailySaleTransaction")
DailySummary = _import_model("daily_sale.DailySummary")
Inventory_List = _import_model("containers.Inventory_List")
Container = _import_model("containers.Container")
Saraf = _import_model("containers.Saraf")
SarafTransaction = _import_model("containers.SarafTransaction")
UserProfile = _import_model("accounts.UserProfile")
Company = _import_model("accounts.Company")
Employee = _import_model("employee.Employee")
SalaryPayment = _import_model("employee.SalaryPayment")
# finance app common names — adapt if your finance app uses different names:
CashIn = _import_model("finance.CashIn") or _import_model("financial.CashIn")
CashOut = _import_model("finance.CashOut") or _import_model("financial.CashOut")
ExpenseItem = _import_model("expenses.ExpenseItem") or _import_model("finance.ExpenseItem")


# --------------------------
# Helper utilities
# --------------------------
def _date_from_param(d: Optional[date], default: Optional[date] = None) -> Optional[date]:
    if not d:
        return default
    if isinstance(d, date):
        return d
    try:
        return datetime.fromisoformat(str(d)).date()
    except Exception:
        return default


def _normalize_decimal(v) -> Decimal:
    try:
        if v is None:
            return DEC_ZERO
        if isinstance(v, Decimal):
            return v
        return Decimal(v)
    except Exception:
        return DEC_ZERO


def _range_by_period(period: str, target: Optional[date] = None) -> Tuple[date, date]:
    """
    period: 'daily'|'weekly'|'monthly'|'yearly'
    Returns (start_date, end_date)
    """
    end = target or timezone.now().date()
    if period == "daily":
        start = end
    elif period == "weekly":
        start = end - timedelta(days=6)
    elif period == "monthly":
        start = (end.replace(day=1))
    elif period == "yearly":
        start = end.replace(month=1, day=1)
    else:
        start = end - timedelta(days=29)
    return start, end


# --------------------------
# Core aggregated reports
# --------------------------
def daily_summary(target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Return a dictionary summary for a single day.
    Aggregates from DailySaleTransaction (sales/purchases), cash-ins/outs (if present),
    inventory valuation snapshot, saraf balances and basic payroll liabilities.
    """
    target = _date_from_param(target_date, timezone.now().date())
    start, end = target, target

    result: Dict[str, Any] = {"date": target.isoformat()}

    # Daily sales aggregates
    if DailySaleTransaction:
        try:
            qs = DailySaleTransaction.objects.filter(date=target)
            ag = qs.aggregate(
                total_sales=Coalesce(Sum('total_amount', filter=F('transaction_type') == Value('sale')), Value(DEC_ZERO), output_field=DecimalField()),
                total_purchases=Coalesce(Sum('total_amount', filter=F('transaction_type') == Value('purchase')), Value(DEC_ZERO), output_field=DecimalField()),
                total_tax=Coalesce(Sum('tax'), Value(DEC_ZERO), output_field=DecimalField()),
                total_discount=Coalesce(Sum('discount'), Value(DEC_ZERO), output_field=DecimalField()),
                total_advance=Coalesce(Sum('advance'), Value(DEC_ZERO), output_field=DecimalField()),
                total_balance=Coalesce(Sum('balance'), Value(DEC_ZERO), output_field=DecimalField()),
                transactions_count=Coalesce(Count('id'), Value(0))
            )
            # Because of limitations with Conditional aggregation via F==Value in generic code,
            # compute sales/purchases more robustly:
            ag_sales = qs.filter(transaction_type='sale').aggregate(total=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()))
            ag_purch = qs.filter(transaction_type='purchase').aggregate(total=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()))
            result.update({
                "total_sales": _normalize_decimal(ag_sales.get('total')),
                "total_purchases": _normalize_decimal(ag_purch.get('total')),
                "total_tax": _normalize_decimal(ag.get('total_tax')),
                "total_discount": _normalize_decimal(ag.get('total_discount')),
                "total_advance": _normalize_decimal(ag.get('total_advance')),
                "total_balance": _normalize_decimal(ag.get('total_balance')),
                "transactions_count": int(ag.get('transactions_count') or 0)
            })
        except Exception as e:
            logger.exception("daily_summary: DailySaleTransaction aggregation failed: %s", e)
            result.update({
                "total_sales": DEC_ZERO,
                "total_purchases": DEC_ZERO,
                "total_tax": DEC_ZERO,
                "total_discount": DEC_ZERO,
                "total_advance": DEC_ZERO,
                "total_balance": DEC_ZERO,
                "transactions_count": 0
            })
    else:
        result.update({
            "total_sales": DEC_ZERO,
            "total_purchases": DEC_ZERO,
            "total_tax": DEC_ZERO,
            "total_discount": DEC_ZERO,
            "total_advance": DEC_ZERO,
            "total_balance": DEC_ZERO,
            "transactions_count": 0
        })

    # Cashflow (cash-in / cash-out) if finance models exist
    cashin_total = DEC_ZERO
    cashout_total = DEC_ZERO
    if CashIn:
        try:
            cashin_total = _normalize_decimal(CashIn.objects.filter(date=target).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total'])
        except Exception as e:
            logger.debug("daily_summary: CashIn query failed: %s", e)
    if CashOut:
        try:
            cashout_total = _normalize_decimal(CashOut.objects.filter(date=target).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total'])
        except Exception as e:
            logger.debug("daily_summary: CashOut query failed: %s", e)

    result["cash_in"] = cashin_total
    result["cash_out"] = cashout_total
    result["net_cashflow"] = (cashin_total - cashout_total)

    # Inventory valuation (snapshot)
    if Inventory_List:
        try:
            # value by `in_stock_qty * unit_price`
            inv_ag = Inventory_List.objects.aggregate(
                inventory_value=Coalesce(Sum(F('in_stock_qty') * F('unit_price'), output_field=DecimalField()), Value(DEC_ZERO))
            )
            result["inventory_value"] = _normalize_decimal(inv_ag.get('inventory_value'))
            result["total_products"] = Inventory_List.objects.count()
            # top 10 inventory by value
            top_inv = Inventory_List.objects.annotate(value=F('in_stock_qty') * F('unit_price')).order_by('-value')[:10].values(
                'id', 'product_name', 'in_stock_qty', 'unit_price', 'value'
            )
            result["top_inventory_by_value"] = list(top_inv)
        except Exception as e:
            logger.debug("daily_summary: Inventory aggregation failed: %s", e)
            result["inventory_value"] = DEC_ZERO
            result["total_products"] = 0
            result["top_inventory_by_value"] = []
    else:
        result["inventory_value"] = DEC_ZERO
        result["total_products"] = 0
        result["top_inventory_by_value"] = []

    # Saraf overview (balances)
    if Saraf:
        try:
            saraf_ag = Saraf.objects.annotate(
                total_received=Coalesce(Sum('transactions__received_from_saraf'), Value(DEC_ZERO), output_field=DecimalField()),
                total_paid=Coalesce(Sum('transactions__paid_by_company'), Value(DEC_ZERO), output_field=DecimalField()),
                total_debit=Coalesce(Sum('transactions__debit_company'), Value(DEC_ZERO), output_field=DecimalField()),
            ).annotate(balance=F('total_received') + F('total_debit') - F('total_paid'))
            # return top sarafs by absolute balance (desc)
            result["saraf_overview"] = list(saraf_ag.values('id', 'user_id', 'total_received', 'total_paid', 'total_debit', 'balance')[:50])
        except Exception as e:
            logger.debug("daily_summary: Saraf aggregation failed: %s", e)
            result["saraf_overview"] = []
    else:
        result["saraf_overview"] = []

    # Employee payroll liabilities (next due etc.)
    if Employee:
        try:
            unpaid_salaries = SalaryPayment.objects.filter(is_paid=False, date__lte=target).aggregate(total_due=Coalesce(Sum('salary_amount'), Value(DEC_ZERO)))
            result["employee_salary_due"] = _normalize_decimal(unpaid_salaries.get('total_due'))
            # per-employee brief
            emp_brief = SalaryPayment.objects.filter(date__lte=target, is_paid=False).values('employee__id', 'employee__employee__user__username').annotate(total_due=Coalesce(Sum('salary_amount'), Value(DEC_ZERO))).order_by('-total_due')[:50]
            result["employee_liabilities"] = list(emp_brief)
        except Exception as e:
            logger.debug("daily_summary: Employee aggregation failed: %s", e)
            result["employee_salary_due"] = DEC_ZERO
            result["employee_liabilities"] = []
    else:
        result["employee_salary_due"] = DEC_ZERO
        result["employee_liabilities"] = []

    # Profit estimate (sales - purchases - cashout expenses)
    try:
        profit = result.get("total_sales", DEC_ZERO) - result.get("total_purchases", DEC_ZERO) - result.get("cash_out", DEC_ZERO)
        result["estimated_profit"] = profit
    except Exception:
        result["estimated_profit"] = DEC_ZERO

    return result


def range_summary(start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Generic range summary aggregated across multiple days (inclusive).
    Returns totals and daily series (by day).
    """
    result: Dict[str, Any] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }

    if DailySaleTransaction:
        try:
            qs = DailySaleTransaction.objects.filter(date__range=[start_date, end_date])
            ag = qs.aggregate(
                total_sales=Coalesce(Sum('total_amount', filter=F('transaction_type') == Value('sale')), Value(DEC_ZERO), output_field=DecimalField()),
                total_purchases=Coalesce(Sum('total_amount', filter=F('transaction_type') == Value('purchase')), Value(DEC_ZERO), output_field=DecimalField()),
                total_tax=Coalesce(Sum('tax'), Value(DEC_ZERO), output_field=DecimalField()),
                transactions_count=Coalesce(Count('id'), Value(0))
            )
            # safer split:
            total_sales = qs.filter(transaction_type='sale').aggregate(total=Coalesce(Sum('total_amount'), Value(DEC_ZERO)))['total']
            total_purchases = qs.filter(transaction_type='purchase').aggregate(total=Coalesce(Sum('total_amount'), Value(DEC_ZERO)))['total']
            result.update({
                "total_sales": _normalize_decimal(total_sales),
                "total_purchases": _normalize_decimal(total_purchases),
                "total_tax": _normalize_decimal(ag.get('total_tax')),
                "transactions_count": int(ag.get('transactions_count') or 0)
            })

            # daily series
            series_qs = qs.filter(transaction_type='sale').values('date').annotate(
                daily_sales=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
                daily_count=Coalesce(Count('id'), Value(0))
            ).order_by('date')
            result["daily_series"] = [{'date': x['date'].isoformat(), 'sales': _normalize_decimal(x['daily_sales']), 'count': int(x['daily_count'])} for x in series_qs]
        except Exception as e:
            logger.exception("range_summary aggregation failed: %s", e)
            result.update({
                "total_sales": DEC_ZERO,
                "total_purchases": DEC_ZERO,
                "total_tax": DEC_ZERO,
                "transactions_count": 0,
                "daily_series": []
            })
    else:
        result.update({
            "total_sales": DEC_ZERO,
            "total_purchases": DEC_ZERO,
            "total_tax": DEC_ZERO,
            "transactions_count": 0,
            "daily_series": []
        })

    # cashflow for range
    if CashIn or CashOut:
        try:
            cashin_total = CashIn.objects.filter(date__range=[start_date, end_date]).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total'] if CashIn else DEC_ZERO
            cashout_total = CashOut.objects.filter(date__range=[start_date, end_date]).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total'] if CashOut else DEC_ZERO
            result["cash_in"] = _normalize_decimal(cashin_total)
            result["cash_out"] = _normalize_decimal(cashout_total)
            result["net_cashflow"] = result["cash_in"] - result["cash_out"]
        except Exception as e:
            logger.debug("range_summary cashflow failed: %s", e)
            result.update({"cash_in": DEC_ZERO, "cash_out": DEC_ZERO, "net_cashflow": DEC_ZERO})
    else:
        result.update({"cash_in": DEC_ZERO, "cash_out": DEC_ZERO, "net_cashflow": DEC_ZERO})

    return result


def weekly_summary(target_date: Optional[date] = None) -> Dict[str, Any]:
    start, end = _range_by_period("weekly", _date_from_param(target_date, None))
    return range_summary(start, end)


def monthly_summary(target_date: Optional[date] = None) -> Dict[str, Any]:
    start, end = _range_by_period("monthly", _date_from_param(target_date, None))
    return range_summary(start, end)


def yearly_summary(target_date: Optional[date] = None) -> Dict[str, Any]:
    start, end = _range_by_period("yearly", _date_from_param(target_date, None))
    return range_summary(start, end)


# --------------------------
# Cashflow & P&L (profit and loss)
# --------------------------
def cashflow_summary(start_date: Optional[date] = None, end_date: Optional[date] = None) -> Dict[str, Any]:
    if start_date is None or end_date is None:
        start_date, end_date = _range_by_period("monthly")[0], _range_by_period("monthly")[1]
    return range_summary(start_date, end_date)


def profit_and_loss(start_date: date, end_date: date) -> Dict[str, Any]:
    """
    Profit & Loss over a date range.
    P&L = Revenues (sales) - COGS (if available via item.unit_price*qty or purchases) - Operating expenses (cashout/expense items)
    """
    res = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
    # Revenues
    if DailySaleTransaction:
        try:
            revenues = DailySaleTransaction.objects.filter(date__range=[start_date, end_date], transaction_type='sale').aggregate(total=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()))['total']
            res["revenues"] = _normalize_decimal(revenues)
        except Exception as e:
            logger.debug("profit_and_loss: revenue failed: %s", e)
            res["revenues"] = DEC_ZERO
    else:
        res["revenues"] = DEC_ZERO

    # COGS: try to estimate from Inventory_List.unit_price * qty sold (if Inventory_List tracks cost)
    cogs = DEC_ZERO
    if Inventory_List:
        try:
            # If Inventory_List has 'unit_price' (cost) and we can sum qty sold by joining transactions -> item
            sold_qs = DailySaleTransaction.objects.filter(date__range=[start_date, end_date], transaction_type='sale', item__isnull=False)
            # Estimate COGS = sum(item.unit_price * tx.quantity) — this assumes item.unit_price holds cost
            sold_items = sold_qs.values('item').annotate(cost_total=Coalesce(Sum(F('quantity') * F('item__unit_price'), output_field=DecimalField()), Value(DEC_ZERO)))
            # Sum costs
            cogs_val = sum([_normalize_decimal(x.get('cost_total')) for x in sold_items])
            cogs = _normalize_decimal(cogs_val)
            res["cogs"] = cogs
        except Exception as e:
            logger.debug("profit_and_loss: COGS calculation failed: %s", e)
            res["cogs"] = DEC_ZERO
    else:
        res["cogs"] = DEC_ZERO

    # Operating expenses: cashout + ExpenseItem sums
    operating_expenses = DEC_ZERO
    if CashOut:
        try:
            cashout_total = CashOut.objects.filter(date__range=[start_date, end_date]).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total']
            operating_expenses += _normalize_decimal(cashout_total)
        except Exception:
            logger.debug("profit_and_loss: CashOut failed")
    if ExpenseItem:
        try:
            expense_total = ExpenseItem.objects.filter(date__range=[start_date, end_date]).aggregate(total=Coalesce(Sum('amount'), Value(DEC_ZERO)))['total']
            operating_expenses += _normalize_decimal(expense_total)
        except Exception:
            logger.debug("profit_and_loss: ExpenseItem failed")
    res["operating_expenses"] = operating_expenses

    # Net profit
    try:
        res["net_profit"] = res["revenues"] - res["cogs"] - res["operating_expenses"]
    except Exception:
        res["net_profit"] = DEC_ZERO

    return res


# --------------------------
# Inventory / sales leaderboards
# --------------------------
def top_selling_items(start_date: date, end_date: date, limit: int = 20) -> List[Dict[str, Any]]:
    if not DailySaleTransaction:
        return []
    try:
        qs = DailySaleTransaction.objects.filter(date__range=[start_date, end_date], transaction_type='sale', item__isnull=False)
        top = qs.values('item__id', 'item__product_name').annotate(
            qty=Coalesce(Sum('quantity'), Value(0)),
            revenue=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField())
        ).order_by('-revenue')[:limit]
        return list(top)
    except Exception as e:
        logger.debug("top_selling_items failed: %s", e)
        return []


# --------------------------
# Saraf & Accounts overview
# --------------------------
def saraf_overview(limit: int = 100) -> List[Dict[str, Any]]:
    if not Saraf:
        return []
    try:
        agg = Saraf.objects.annotate(
            total_received=Coalesce(Sum('transactions__received_from_saraf'), Value(DEC_ZERO), output_field=DecimalField()),
            total_paid=Coalesce(Sum('transactions__paid_by_company'), Value(DEC_ZERO), output_field=DecimalField()),
            total_debit=Coalesce(Sum('transactions__debit_company'), Value(DEC_ZERO), output_field=DecimalField())
        ).annotate(balance=F('total_received') + F('total_debit') - F('total_paid')).order_by('-balance')[:limit]
        return list(agg.values('id', 'user_id', 'total_received', 'total_paid', 'total_debit', 'balance'))
    except Exception as e:
        logger.debug("saraf_overview failed: %s", e)
        return []


# --------------------------
# Employee payroll overview
# --------------------------
def payroll_overview(as_of_date: Optional[date] = None) -> Dict[str, Any]:
    as_of = _date_from_param(as_of_date, timezone.now().date())
    res = {"as_of": as_of.isoformat()}
    if not Employee:
        res.update({"total_salary_due": DEC_ZERO, "upcoming_payments": []})
        return res
    try:
        # total unpaid salary payments up to as_of
        unpaid = SalaryPayment.objects.filter(is_paid=False, date__lte=as_of).aggregate(total=Coalesce(Sum('salary_amount'), Value(DEC_ZERO)))['total']
        res["total_salary_due"] = _normalize_decimal(unpaid)
        # next 30 days scheduled payments
        upcoming = SalaryPayment.objects.filter(date__range=[as_of, as_of + timedelta(days=30)]).values(
            'date', 'employee__id', 'employee__employee__user__username'
        ).annotate(total=Coalesce(Sum('salary_amount'), Value(DEC_ZERO))).order_by('date')[:200]
        res["upcoming_payments"] = list(upcoming)
    except Exception as e:
        logger.debug("payroll_overview failed: %s", e)
        res["total_salary_due"] = DEC_ZERO
        res["upcoming_payments"] = []
    return res


# --------------------------
# Helpers: CSV / export
# --------------------------
def export_to_csv_rows(summary: Dict[str, Any]) -> List[List[Any]]:
    """
    Convert a summary dict into CSV-like rows (list of lists).
    This is a simple helper; adapt to your CSV/Excel generator.
    """
    rows = [["Key", "Value"]]
    for k, v in summary.items():
        rows.append([str(k), str(v)])
    return rows


# --------------------------
# System full report (single entrypoint)
# --------------------------
def system_full_report(target_date: Optional[date] = None, days: int = 30) -> Dict[str, Any]:
    """
    Return a comprehensive report object with:
     - daily (target_date)
     - weekly (last `days` days)
     - monthly
     - yearly
     - cashflow & P&L
     - inventory snapshot
     - top sellers
     - saraf overview
     - payroll overview

    Useful for a single API endpoint or admin dashboard ingestion.
    """
    target = _date_from_param(target_date, timezone.now().date())
    report_obj: Dict[str, Any] = {"generated_at": timezone.now().isoformat(), "target_date": target.isoformat()}

    # daily
    report_obj["daily"] = daily_summary(target)

    # weekly/monthly/yearly
    report_obj["weekly"] = weekly_summary(target)
    report_obj["monthly"] = monthly_summary(target)
    report_obj["yearly"] = yearly_summary(target)

    # cashflow & P&L for last `days`
    start = target - timedelta(days=days - 1)
    report_obj["range_summary"] = range_summary(start, target)
    report_obj["profit_and_loss"] = profit_and_loss(start, target)

    # inventory & top sellers
    report_obj["inventory_valuation"] = {"value": report_obj["daily"].get("inventory_value", DEC_ZERO), "total_products": report_obj["daily"].get("total_products", 0)}
    report_obj["top_sellers"] = top_selling_items(start, target, limit=25)

    # saraf & payroll
    report_obj["saraf_overview"] = saraf_overview(limit=100)
    report_obj["payroll_overview"] = payroll_overview(target)

    return report_obj


# --------------------------
# Scheduled / batch helpers
# --------------------------
def update_daily_summary(run_date: Optional[date] = None) -> DailySummary:
    """
    Ensure a DailySummary row exists and is computed for the given date.
    Returns the DailySummary instance (or raises if DailySummary model missing).
    Use this in views after create/edit/delete of transactions, or schedule nightly.
    """
    if not DailySummary:
        raise RuntimeError("DailySummary model not available")

    target = _date_from_param(run_date, timezone.now().date())
    obj, created = DailySummary.objects.get_or_create(date=target)
    try:
        # calling model method calculate_totals (you included in model)
        obj.calculate_totals()
        obj.save()
    except Exception as e:
        logger.exception("update_daily_summary failed for %s: %s", target, e)
    return obj


# Example scheduler hook (pseudo)
SCHEDULER_HINT = """
Schedule suggestion:
- Run nightly: update_daily_summary() for yesterday
  (use cron: 0 2 * * * python manage.py shell -c 'from daily_sale.report import update_daily_summary; update_daily_summary()')
- Or use Celery beat:
  @periodic_task(crontab(hour=2, minute=0)) -> update_daily_summary()
"""

# End of report.py
