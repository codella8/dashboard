import logging
from decimal import Decimal
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction as db_transaction
from django.db.models import Sum
from .models import DailySaleTransaction, Payment, DailySummary, OutstandingCustomer
from .utils import recompute_daily_summary_for_date, recompute_outstanding_for_customer

logger = logging.getLogger(__name__)

# ---------------------------
# Pre-save: ذخیره مقادیر قبلی برای مقایسه
# ---------------------------
@receiver(pre_save, sender=DailySaleTransaction)
def dst_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = DailySaleTransaction.objects.only("date", "customer_id").get(pk=instance.pk)
            instance._old_date = old.date
            instance._old_customer_id = old.customer_id
        except DailySaleTransaction.DoesNotExist:
            instance._old_date = None
            instance._old_customer_id = None
    else:
        instance._old_date = None
        instance._old_customer_id = None

# ---------------------------
# Post-save تراکنش
# ---------------------------
@receiver(post_save, sender=DailySaleTransaction)
def dst_post_save(sender, instance, created, **kwargs):
    try:
        dates_to_update = {instance.date}
        if getattr(instance, "_old_date", None) and instance._old_date != instance.date:
            dates_to_update.add(instance._old_date)

        customers_to_update = {instance.customer_id}
        if getattr(instance, "_old_customer_id", None) and instance._old_customer_id != instance.customer_id:
            customers_to_update.add(instance._old_customer_id)

        with db_transaction.atomic():
            for d in dates_to_update:
                recompute_daily_summary_for_date(d)
            for cid in customers_to_update:
                recompute_outstanding_for_customer(cid)

        logger.info("Transaction %s processed successfully", instance.invoice_number)

    except Exception:
        logger.exception("Error processing DailySaleTransaction post_save (%s)", instance.invoice_number)

# ---------------------------
# Post-delete تراکنش
# ---------------------------
@receiver(post_delete, sender=DailySaleTransaction)
def dst_post_delete(sender, instance, **kwargs):
    try:
        with db_transaction.atomic():
            recompute_daily_summary_for_date(instance.date)
            recompute_outstanding_for_customer(instance.customer_id)

        logger.info("Transaction deleted and summaries updated")
    except Exception:
        logger.exception("Error processing DailySaleTransaction post_delete")

# ---------------------------
# Post-save و post-delete پرداخت‌ها
# ---------------------------
@receiver([post_save, post_delete], sender=Payment)
def payment_update_summaries(sender, instance, **kwargs):
    tx = instance.transaction
    if not tx:
        return
    try:
        with db_transaction.atomic():
            if tx.date:
                recompute_daily_summary_for_date(tx.date)
            if tx.customer_id:
                recompute_outstanding_for_customer(tx.customer_id)
        logger.info("Payment processed for transaction %s", tx.invoice_number)
    except Exception:
        logger.exception("Error processing Payment (%s)", tx.invoice_number)

# ---------------------------
# Post-save برای به‌روزرسانی بدهی مشتری
# ---------------------------
def update_customer_debt(transaction_instance):
    try:
        customer = transaction_instance.customer
        paid_amount = Payment.objects.filter(transaction=transaction_instance).aggregate(
            total_paid=Sum('amount')
        )['total_paid'] or Decimal('0.00')

        remaining_amount = (transaction_instance.total_amount or Decimal('0.00')) - paid_amount - (getattr(transaction_instance, 'discount', Decimal('0.00')) or Decimal('0.00'))
        customer.debt = remaining_amount if remaining_amount > Decimal('0.00') else Decimal('0.00')
        customer.save()
    except Exception:
        logger.exception("Error updating debt for customer %s", getattr(transaction_instance.customer, 'id', 'unknown'))

# استفاده از تابع مشترک برای تراکنش و پرداخت
@receiver(post_save, sender=DailySaleTransaction)
def update_debt_on_transaction(sender, instance, **kwargs):
    update_customer_debt(instance)

@receiver(post_save, sender=Payment)
def update_debt_on_payment(sender, instance, **kwargs):
    tx = instance.transaction
    if tx:
        update_customer_debt(tx)
