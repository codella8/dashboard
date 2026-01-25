# daily_sale/signals.py
import logging
from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal
from .models import (
    DailySaleTransaction,
    Payment,
    DailySummary,
    OutstandingCustomer,
)
from .utils import (
    recompute_daily_summary_for_date,
    recompute_outstanding_for_customer,
)

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=DailySaleTransaction)
def dst_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_date = None
        instance._old_customer_id = None
        return

    try:
        old = DailySaleTransaction.objects.only("date", "customer_id").get(pk=instance.pk)
        instance._old_date = old.date
        instance._old_customer_id = old.customer_id
    except DailySaleTransaction.DoesNotExist:
        instance._old_date = None
        instance._old_customer_id = None


@receiver(post_save, sender=DailySaleTransaction)
def dst_post_save(sender, instance, created, **kwargs):
    try:
        dates_to_update = set()

        if instance.date:
            dates_to_update.add(instance.date)

        old_date = getattr(instance, "_old_date", None)
        if old_date and old_date != instance.date:
            dates_to_update.add(old_date)

        for d in dates_to_update:
            recompute_daily_summary_for_date(d)

        customers_to_update = set()

        if instance.customer_id:
            customers_to_update.add(instance.customer_id)

        old_customer_id = getattr(instance, "_old_customer_id", None)
        if old_customer_id and old_customer_id != instance.customer_id:
            customers_to_update.add(old_customer_id)

        for cid in customers_to_update:
            recompute_outstanding_for_customer(cid)

        logger.info(
            "Transaction %s processed successfully",
            instance.invoice_number,
        )

    except Exception as exc:
        logger.exception(
            "Error processing DailySaleTransaction post_save (%s)",
            instance.invoice_number,
        )


@receiver(pre_delete, sender=DailySaleTransaction)
def dst_pre_delete(sender, instance, **kwargs):
    instance._delete_date = instance.date
    instance._delete_customer_id = instance.customer_id


@receiver(post_delete, sender=DailySaleTransaction)
def dst_post_delete(sender, instance, **kwargs):
    try:
        if getattr(instance, "_delete_date", None):
            recompute_daily_summary_for_date(instance._delete_date)

        if getattr(instance, "_delete_customer_id", None):
            recompute_outstanding_for_customer(instance._delete_customer_id)

        logger.info("Transaction deleted and summaries updated")

    except Exception:
        logger.exception("Error processing DailySaleTransaction post_delete")

@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    try:
        tx = instance.transaction
        if not tx:
            return

        if tx.date:
            recompute_daily_summary_for_date(tx.date)

        if tx.customer_id:
            recompute_outstanding_for_customer(tx.customer_id)

        logger.info("Payment processed for transaction %s", tx.invoice_number)

    except Exception:
        logger.exception("Error processing Payment post_save")


@receiver(post_delete, sender=Payment)
def payment_post_delete(sender, instance, **kwargs):
    try:
        tx = instance.transaction
        if not tx:
            return

        if tx.date:
            recompute_daily_summary_for_date(tx.date)

        if tx.customer_id:
            recompute_outstanding_for_customer(tx.customer_id)

        logger.info("Payment deleted for transaction %s", tx.invoice_number)

    except Exception:
        logger.exception("Error processing Payment post_delete")

@receiver(post_save, sender=DailySummary)
def daily_summary_post_save(sender, instance, created, **kwargs):
    if created:
        logger.info("DailySummary created for %s", instance.date)
    else:
        logger.debug("DailySummary updated for %s", instance.date)


@receiver(post_save, sender=OutstandingCustomer)
def outstanding_post_save(sender, instance, created, **kwargs):
    customer = getattr(instance.customer, "user", instance.customer)
    if created:
        logger.info("Outstanding created for %s", customer)
    else:
        logger.debug("Outstanding updated for %s", customer)
        
@receiver(post_save, sender=Payment)
def update_customer_debt_on_payment(sender, instance, created, **kwargs):
    transaction = instance.transaction
    paid_amount = Payment.objects.filter(transaction=transaction).aggregate(
        total_paid=Sum('amount')
    )['total_paid'] or Decimal('0')
    
    remaining_amount = transaction.total_amount - paid_amount - (transaction.discount or Decimal('0'))

    customer = transaction.customer
    if remaining_amount > Decimal('0'):
        customer.debt = remaining_amount
    else:
        customer.debt = Decimal('0')

    customer.save()


@receiver(post_save, sender=DailySaleTransaction)
def update_customer_debt_on_transaction(sender, instance, created, **kwargs):
    customer = instance.customer
    paid_amount = Payment.objects.filter(transaction=instance).aggregate(
        total_paid=Sum('amount')
    )['total_paid'] or Decimal('0')
    
    remaining_amount = instance.total_amount - paid_amount - (instance.discount or Decimal('0'))
    
    if remaining_amount > Decimal('0'):
        customer.debt = remaining_amount
    else:
        customer.debt = Decimal('0')

    customer.save()
