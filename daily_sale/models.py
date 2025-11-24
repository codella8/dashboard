from uuid import uuid4
from decimal import Decimal, InvalidOperation
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from accounts.models import UserProfile, Company
from containers.models import Inventory_List, Container

class DailySaleTransaction(models.Model):
    TRANSACTION_TYPES = [
        ("sale", "Sale"),
        ("purchase", "purchase"),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('paid', 'paid'),
        ('cancelled', 'cancelled'),
    ]
    
    CURRENCY_CHOICES = [
        ('usd', 'usd'),
        ('eur', 'eur'),
        ('aed', 'aed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Invoice Nubber")
    date = models.DateField(default=timezone.now, db_index=True, verbose_name="Date")
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, default="sale", verbose_name="Transaction Type")

    item = models.ForeignKey(Inventory_List, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Item")
    customer = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Customer")
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Company")
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Container")
    
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="Unit Price")
    advance = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="Advance")
    discount = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="Discount")
    tax = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="Tax")
    
    # مقادیر محاسبه شده خودکار
    subtotal = models.DecimalField(max_digits=15, decimal_places=0, default=0, editable=False, verbose_name="Subtotal")
    total_amount = models.DecimalField(max_digits=15, decimal_places=0, default=0, editable=False, verbose_name="Total Amount")
    balance = models.DecimalField(max_digits=15, decimal_places=0, default=0, editable=False, verbose_name="Balance")
    
    # اطلاعات تکمیلی
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='usd', verbose_name="Currency")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Status")
    description = models.CharField(max_length=255, blank=True, verbose_name="Discription")
    note = models.TextField(blank=True, verbose_name="Note")
    
    # اطلاعات سیستمی
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Created_by")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['status']),
            models.Index(fields=['invoice_number']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.get_transaction_type_display()}"

    def calculate_financials(self):
        try:
            # محاسبه جمع جزء
            self.subtotal = (self.quantity * self.unit_price).quantize(Decimal('0'))
            
            # محاسبه جمع کل (بعد از تخفیف و مالیات)
            amount_after_discount = self.subtotal - self.discount
            if amount_after_discount < 0:
                amount_after_discount = Decimal('0')
            
            self.total_amount = (amount_after_discount + self.tax).quantize(Decimal('0'))
            
            # محاسبه مانده
            self.balance = (self.total_amount - self.advance).quantize(Decimal('0'))
            if self.balance < 0:
                self.balance = Decimal('0')
                
        except (InvalidOperation, TypeError):
            # مقداردهی پیش‌فرض در صورت خطا
            self.subtotal = Decimal('0')
            self.total_amount = Decimal('0')
            self.balance = Decimal('0')

    def update_inventory(self):
        """به‌روزرسانی خودکار موجودی کالا"""
        if self.transaction_type == "sale" and self.item and self.status == "paid":
            try:
                with transaction.atomic():
                    inventory_item = self.item
                    if inventory_item.in_stock_qty >= self.quantity:
                        inventory_item.in_stock_qty -= self.quantity
                        inventory_item.total_sold_qty += self.quantity
                        inventory_item.total_sold_count += 1
                        
                        # محاسبه میانگین قیمت فروش
                        if self.quantity > 0:
                            sold_price = self.total_amount / self.quantity
                            inventory_item.sold_price = sold_price
                        
                        inventory_item.save()
            except Exception:
                # در صورت خطا در به‌روزرسانی موجودی، ادامه بده
                pass

    def generate_invoice_number(self):
        """تولید خودکار شماره فاکتور"""
        if not self.invoice_number:
            date_str = timezone.now().strftime("%Y%m%d")
            last_invoice = DailySaleTransaction.objects.filter(
                invoice_number__startswith=f"INV-{date_str}"
            ).order_by('-invoice_number').first()
            
            if last_invoice:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
                
            self.invoice_number = f"INV-{date_str}-{new_num:04d}"

    def save(self, *args, **kwargs):
        """ذخیره هوشمند با تمام محاسبات خودکار"""
        # تولید شماره فاکتور
        self.generate_invoice_number()
        
        # محاسبه مقادیر مالی
        self.calculate_financials()
        
        # ذخیره تراکنش
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # به‌روزرسانی موجودی
        self.update_inventory()
        
        # به‌روزرسانی خلاصه روزانه
        if is_new or self._state.adding:
            self.update_daily_summary()

    def update_daily_summary(self):
        """به‌روزرسانی خودکار خلاصه روزانه"""
        from .report import update_daily_summary
        update_daily_summary(self.date)

    @property
    def profit(self):
        """محاسبه سود خودکار"""
        if self.transaction_type == "sale" and self.item:
            try:
                cost = self.item.unit_price * self.quantity
                return (self.total_amount - cost).quantize(Decimal('0'))
            except:
                return Decimal('0')
        return Decimal('0')

    @property
    def is_fully_paid(self):
        """بررسی پرداخت کامل"""
        return self.balance == Decimal('0') and self.total_amount > Decimal('0')

    def mark_as_paid(self):
        """علامت‌گذاری به عنوان پرداخت شده"""
        self.status = 'paid'
        self.balance = Decimal('0')
        self.save()

class DailySummary(models.Model):
    """خلاصه روزانه هوشمند"""
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date = models.DateField(unique=True, db_index=True, verbose_name="Date")
    
    # آمار مالی
    total_sales = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total Sales")
    total_purchases = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total Purcheses")
    total_expenses = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total Expenses")
    total_profit = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total Profit")
    net_balance = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Net Balance")
    
    # آمار کمی
    transactions_count = models.PositiveIntegerField(default=0, verbose_name="Transaction Quantity")
    items_sold = models.PositiveIntegerField(default=0, verbose_name="Items Sold")
    customers_count = models.PositiveIntegerField(default=0, verbose_name="Customer Quantity")
    
    # اطلاعات ارزی
    usd_total = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total USD")
    eur_total = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total EUR")
    aed_total = models.DecimalField(max_digits=18, decimal_places=0, default=0, verbose_name="Total AED")
    
    note = models.TextField(blank=True, verbose_name="Note")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")
    is_final = models.BooleanField(default=False, verbose_name="Is final")

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['is_final']),
        ]

    def __str__(self):
        return f"Total{self.date} - Profit: {self.total_profit}"

    def calculate_totals(self):
        """محاسبه خودکار تمام آمار از تراکنش‌ها"""
        from django.db.models import Sum, Count
        from django.db.models.functions import Coalesce
        
        transactions = DailySaleTransaction.objects.filter(date=self.date)
        
        # محاسبه مالی
        sales_data = transactions.filter(transaction_type="sale").aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'))
        )
        purchase_data = transactions.filter(transaction_type="purchase").aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'))
        )
        balance_data = transactions.aggregate(
            total=Coalesce(Sum('balance'), Decimal('0'))
        )
        
        self.total_sales = sales_data['total']
        self.total_purchases = purchase_data['total']
        self.net_balance = balance_data['total']
        self.total_profit = self.total_sales - self.total_purchases - self.total_expenses
        
        # محاسبه کمی
        self.transactions_count = transactions.count()
        self.items_sold = transactions.filter(transaction_type="sale").aggregate(
            total=Coalesce(Sum('quantity'), 0)
        )['total'] or 0
        self.customers_count = transactions.values('customer').distinct().count()
        
        # محاسبه ارزی
        self.usd_total = transactions.filter(currency='usd').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'))
        )['total']
        self.eur_total = transactions.filter(currency='eur').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'))
        )['total']
        self.aed_total = transactions.filter(currency='aed').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'))
        )['total']

    def save(self, *args, **kwargs):
        """ذخیره هوشمند با محاسبه خودکار"""
        if not self.is_final:
            self.calculate_totals()
        
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """محاسبه خودکار حاشیه سود"""
        if self.total_sales > 0:
            return ((self.total_profit / self.total_sales) * 100).quantize(Decimal('0'))
        return Decimal('0')

    @property
    def average_transaction_value(self):
        """محاسبه خودکار میانگین ارزش تراکنش"""
        if self.transactions_count > 0:
            return (self.total_sales / self.transactions_count).quantize(Decimal('0'))
        return Decimal('0')

    def finalize(self):
        """نهایی کردن خلاصه روزانه"""
        self.is_final = True
        self.save()