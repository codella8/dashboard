# daily_sale/services.py
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

class CalculationService:
    """
    سرویس مرکزی برای محاسبات مالی
    این کلاس تمام محاسبات را با یک منطق واحد انجام می‌دهد
    منطق محاسبات دقیقاً مطابق فرم ایجاد تراکنش است
    """
    
    @staticmethod
    def calculate_transaction_amounts(quantity, unit_price, discount, tax_percent, advance):
        """
        محاسبه مقادیر تراکنش با منطق مشابه فرم
        این متد برای پیش‌نمایش و محاسبات سمت سرور استفاده می‌شود
        """
        # محاسبه subtotal
        subtotal = (Decimal(quantity) * Decimal(unit_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # محاسبه مبلغ مشمول مالیات (net amount = subtotal - discount)
        taxable_amount = (subtotal - Decimal(discount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if taxable_amount < Decimal("0"):
            taxable_amount = Decimal("0")

        # محاسبه مالیات (tax = taxable_amount * tax_rate)
        tax_rate = Decimal(tax_percent) / Decimal("100")
        tax_amount = (taxable_amount * tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # محاسبه کل مبلغ (total = taxable_amount + tax_amount)
        total_amount = (taxable_amount + tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # محاسبه مانده حساب (balance = max(total - advance, 0))
        balance = (total_amount - Decimal(advance)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if balance < Decimal("0"):
            balance = Decimal("0")

        # تعیین وضعیت پرداخت
        if balance <= Decimal("0") and total_amount > Decimal("0"):
            payment_status = "paid"
        elif Decimal(advance) > Decimal("0"):
            payment_status = "partial"
        else:
            payment_status = "unpaid"

        return {
            "subtotal": subtotal,
            "taxable_amount": taxable_amount,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
            "balance": balance,
            "payment_status": payment_status,
        }

    @staticmethod
    def calculate_item_amounts(quantity, unit_price, discount, tax_percent):
        """
        محاسبه مقادیر آیتم (بدون advance)
        """
        subtotal = (Decimal(quantity) * Decimal(unit_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        taxable = (subtotal - Decimal(discount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if taxable < Decimal("0"):
            taxable = Decimal("0")

        tax_rate = Decimal(tax_percent) / Decimal("100")
        tax_amount = (taxable * tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        total_amount = (taxable + tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "subtotal": subtotal,
            "taxable": taxable,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
        }

    @staticmethod
    def calculate_transaction_from_items(items_data, tax_percent, advance):
        """
        محاسبه مقادیر تراکنش از روی آیتم‌ها
        items_data: لیست آیتم‌ها با کلیدهای quantity, unit_price, discount
        """
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        tax_amount_total = Decimal("0")

        for item in items_data:
            item_calc = CalculationService.calculate_item_amounts(
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", 0),
                discount=item.get("discount", 0),
                tax_percent=tax_percent
            )
            subtotal += item_calc["subtotal"]
            discount_total += Decimal(item.get("discount", 0))
            tax_amount_total += item_calc["tax_amount"]

        net_amount = max(subtotal - discount_total, Decimal("0"))
        total_amount = (net_amount + tax_amount_total).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        balance = max(total_amount - Decimal(advance), Decimal("0"))

        # تعیین وضعیت پرداخت
        if balance <= Decimal("0") and total_amount > Decimal("0"):
            payment_status = "paid"
        elif Decimal(advance) > Decimal("0"):
            payment_status = "partial"
        else:
            payment_status = "unpaid"

        return {
            "subtotal": subtotal,
            "discount_total": discount_total,
            "tax_amount": tax_amount_total,
            "total_amount": total_amount,
            "balance": balance,
            "payment_status": payment_status,
        }


class SummaryService:
    """
    سرویس مدیریت خلاصه‌ها و آمار
    این سرویس مستقیماً با کوئری‌های Django کار می‌کند
    """
    
    @staticmethod
    def get_transaction_stats(queryset):
        """
        محاسبه آمار تراکنش‌ها برای نمایش در کارت‌های خلاصه
        این متد در ویوها استفاده می‌شود
        """
        from django.db.models import Sum, Q
        from decimal import Decimal
        
        # ================ محاسبه مجموع فروش ================
        sales_total = queryset.filter(transaction_type='sale').aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0')
        
        # ================ محاسبه مجموع خرید ================
        purchases_total = queryset.filter(transaction_type='purchase').aggregate(
            total=Sum('total_amount')
        )['total'] or Decimal('0')
        
        # ================ محاسبه معوقات (بر اساس balance) ================
        # تراکنش‌هایی که balance > 0 دارند (بدهکار هستند)
        outstanding_qs = queryset.filter(balance__gt=0)
        outstanding_total = outstanding_qs.aggregate(
            total=Sum('balance')
        )['total'] or Decimal('0')
        outstanding_count = outstanding_qs.count()
        
        # ================ محاسبه تعداد کالاهای فروخته شده ================
        items_sold = 0
        for transaction in queryset.filter(transaction_type='sale'):
            if hasattr(transaction, 'items') and transaction.items.exists():
                items_sold += sum(item.quantity for item in transaction.items.all())
            else:
                items_sold += transaction.quantity
        
        # ================ محاسبه میانگین تراکنش ================
        total_count = queryset.count()
        avg_transaction = Decimal('0')
        if total_count > 0:
            total_amount_sum = queryset.aggregate(
                total=Sum('total_amount')
            )['total'] or Decimal('0')
            avg_transaction = total_amount_sum / total_count
        
        # لاگ برای دیباگ
        logger.info("=" * 50)
        logger.info("📊 SummaryService.get_transaction_stats:")
        logger.info(f"   - Total Sales: {sales_total:,.2f} AED")
        logger.info(f"   - Total Purchases: {purchases_total:,.2f} AED")
        logger.info(f"   - Outstanding Balance: {outstanding_total:,.2f} AED")
        logger.info(f"   - Outstanding Count: {outstanding_count}")
        logger.info(f"   - Items Sold: {items_sold}")
        logger.info(f"   - Avg Transaction: {avg_transaction:,.2f} AED")
        logger.info("=" * 50)
        
        return {
            'total_sales': sales_total,
            'total_purchases': purchases_total,
            'total_outstanding': outstanding_total,
            'outstanding_count': outstanding_count,
            'items_sold': items_sold,
            'avg_transaction': avg_transaction,
        }