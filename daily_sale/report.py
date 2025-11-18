# daily_sale/report.py
from decimal import Decimal
from django.db.models import Sum, F, Value, Count, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce, TruncMonth, TruncDate
from .models import DailySaleTransaction, DailySummary
from django.utils import timezone
from datetime import date, datetime

# helper: coalesce decimal sums to zero
ZERO = Decimal("0.00")

def _coalesce_sum(queryset, field_name):
    res = queryset.aggregate(total=Coalesce(Sum(field_name), Value(Decimal("0.00"))))
    return res["total"] or ZERO

# 1) خلاصه روزانه برای یک تاریخ مشخص
def get_daily_aggregates(target_date: date):
    """
    Returns dict:
    {
      "date": date,
      "total_sales": Decimal,
      "total_purchase": Decimal,
      "total_expense": Decimal,  # if expenses are in other model, adapt accordingly
      "total_profit": Decimal,    # total_sales - total_purchase - total_expense
      "net_balance": Decimal,     # sum of balances for that date
      "by_currency": { 'usd': Decimal, ...},
      "transactions_count": int
    }
    """
    qs = DailySaleTransaction.objects.filter(date=target_date)
    total_sales = qs.filter(transaction_type="sale").aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO)))["total"] or ZERO
    total_purchase = qs.filter(transaction_type="purchase").aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO)))["total"] or ZERO
    # total_expense: اگر هزینه‌ها در مدل دیگری ذخیره می‌شوند، باید آن‌را از مدل expenses بگیریم.
    # در این تابع فرض صفر است و می‌توانی بعداً آن را از اپ expenses بگیرید.
    total_expense = ZERO
    total_profit = (total_sales - total_purchase - total_expense).quantize(Decimal("0.01"))
    net_balance = qs.aggregate(total_balance=Coalesce(Sum("balance"), Value(ZERO)))["total_balance"] or ZERO

    # تفکیک براساس ارز
    by_currency = {}
    currencies = qs.values_list("currency", flat=True).distinct()
    for cur in currencies:
        s = qs.filter(currency=cur).aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO)))["total"] or ZERO
        by_currency[cur] = s

    transactions_count = qs.count()

    return {
        "date": target_date,
        "total_sales": total_sales,
        "total_purchase": total_purchase,
        "total_expense": total_expense,
        "total_profit": total_profit,
        "net_balance": net_balance,
        "by_currency": by_currency,
        "transactions_count": transactions_count,
    }

# 2) بازه زمانی: آمار کلی بین دو تاریخ
def get_range_aggregates(start_date: date, end_date: date):
    qs = DailySaleTransaction.objects.filter(date__gte=start_date, date__lte=end_date)
    total_sales = qs.filter(transaction_type="sale").aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO)))["total"] or ZERO
    total_purchase = qs.filter(transaction_type="purchase").aggregate(total=Coalesce(Sum("total_amount"), Value(ZERO)))["total"] or ZERO
    net_balance = qs.aggregate(total_balance=Coalesce(Sum("balance"), Value(ZERO)))["total_balance"] or ZERO
    transactions_count = qs.count()
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_sales": total_sales,
        "total_purchase": total_purchase,
        "net_balance": net_balance,
        "transactions_count": transactions_count,
    }

# 3) فروش گروه‌بندی‌شده بر حسب آیتم (مرتب‌شده بر اساس بیشترین فروش)
def sales_by_item(start_date: date = None, end_date: date = None, top_n: int = 20):
    qs = DailySaleTransaction.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    # گروپ و جمع
    res = (
        qs.values("item__id", "item__name")  # فرض می‌کنم Inventory_List فیلد name دارد؛ در صورت نام متفاوت تغییر بده
        .annotate(total_qty=Coalesce(Sum("quantity"), Value(0)),
                  total_amount=Coalesce(Sum("total_amount"), Value(ZERO)),
                  transactions=Coalesce(Count("id"), Value(0)))
        .order_by("-total_amount")[:top_n]
    )
    return list(res)

# 4) فروش بر اساس کانتینر
def sales_by_container(start_date: date = None, end_date: date = None):
    qs = DailySaleTransaction.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    res = (
        qs.values("container__id", "container__name")
        .annotate(total_amount=Coalesce(Sum("total_amount"), Value(ZERO)),
                  transactions=Coalesce(Count("id"), Value(0)))
        .order_by("-total_amount")
    )
    return list(res)

# 5) مشتریان با بیشترین بدهی (balance > 0)
def outstanding_customers(limit=50):
    qs = DailySaleTransaction.objects.filter(balance__gt=0).values("customer__id", "customer__full_name") \
        .annotate(total_balance=Coalesce(Sum("balance"), Value(ZERO)),
                  open_invoices=Coalesce(Count("id"), Value(0))) \
        .order_by("-total_balance")[:limit]
    return list(qs)

# 6) خلاصه ماهانه (گروه‌بندی بر ماه)
def monthly_summary(year=None):
    qs = DailySaleTransaction.objects.all()
    if year:
        qs = qs.filter(date__year=year)
    res = (
        qs.annotate(month=TruncMonth("date"))
          .values("month")
          .annotate(total_sales=Coalesce(Sum("total_amount", filter=F("transaction_type") == "sale"), Value(ZERO)))
          # اگر فیلتر داخل Sum کار نکرد، از دو کوئری جداگانه استفاده کن
          .annotate(transactions=Coalesce(Count("id"), Value(0)))
          .order_by("month")
    )
    # توجه: بعضی DB ها اجازهٔ filter=F("...")==... را در Sum نمی‌دهند؛ اگر خطا دیدی، می‌توانیم به صورت زیر عمل کنیم:
    # برای هر ماه total_sales = qs.filter(date__month=..., date__year=...).filter(transaction_type="sale").aggregate(...)
    return list(res)

# 7) تولید یا به‌روزرسانی DailySummary از جمع تراکنش‌ها برای یک تاریخ
def compute_and_save_daily_summary(target_date: date):
    agg = get_daily_aggregates(target_date)
    obj, created = DailySummary.objects.update_or_create(
        date=target_date,
        defaults={
            "total_sales": agg["total_sales"],
            "total_purchase": agg["total_purchase"],
            "total_expense": agg["total_expense"],
            "total_profit": agg["total_profit"],
            "net_balance": agg["net_balance"],
            "note": f"Computed on {timezone.now().isoformat()}",
        }
    )
    return obj

# 8) گزارش سریع: تراکنش‌های یک فاکتور
def get_transaction_by_invoice(invoice_number: str):
    try:
        return DailySaleTransaction.objects.get(invoice_number=invoice_number)
    except DailySaleTransaction.DoesNotExist:
        return None
