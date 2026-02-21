# daily_sale/signals.py
import logging
from decimal import Decimal
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.db import transaction as db_transaction
from .models import DailySaleTransaction, Payment
from .utils import recompute_daily_summary_for_date, recompute_outstanding_for_customer

logger = logging.getLogger(__name__)

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

@receiver(post_save, sender=DailySaleTransaction)
def dst_post_save(sender, instance, created, **kwargs):
    try:
        dates_to_update = {instance.date}
        if getattr(instance, "_old_date", None) and instance._old_date != instance.date:
            dates_to_update.add(instance._old_date)

        customers_to_update = set()
        if instance.customer_id:
            customers_to_update.add(instance.customer_id)
        if getattr(instance, "_old_customer_id", None) and instance._old_customer_id != instance.customer_id:
            customers_to_update.add(instance._old_customer_id)

        with db_transaction.atomic():
            for d in dates_to_update:
                recompute_daily_summary_for_date(d)
            for cid in customers_to_update:
                if cid: 
                    recompute_outstanding_for_customer(cid)

        logger.info(f"Transaction {instance.invoice_number} processed successfully")

    except Exception as e:
        logger.exception(f"Error processing DailySaleTransaction post_save ({instance.invoice_number}): {str(e)}")
        
@receiver(post_delete, sender=DailySaleTransaction)
def dst_post_delete(sender, instance, **kwargs):
    try:
        with db_transaction.atomic():
            if instance.date:
                recompute_daily_summary_for_date(instance.date)
            if instance.customer_id:
                recompute_outstanding_for_customer(instance.customer_id)

        logger.info("Transaction deleted and summaries updated")
    except Exception as e:
        logger.exception(f"Error processing DailySaleTransaction post_delete: {str(e)}")

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
        logger.info(f"Payment processed for transaction {tx.invoice_number}")
    except Exception as e:
        logger.exception(f"Error processing Payment ({tx.invoice_number}): {str(e)}")