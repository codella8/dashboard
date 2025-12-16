# daily_sale/signals.py
import logging
from django.db.models.signals import pre_save, post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.db import transaction as db_transaction
from .models import DailySaleTransaction, Payment, DailySummary, OutstandingCustomer
from .utils import recompute_daily_summary_for_date, recompute_outstanding_for_customer
from datetime import timedelta

logger = logging.getLogger(__name__)

@receiver(pre_save, sender=DailySaleTransaction)
def dst_pre_save(sender, instance, **kwargs):
    """
    قبل از ذخیره تراکنش، تاریخ قدیم را ذخیره کن
    """
    if instance.pk:
        try:
            old_instance = DailySaleTransaction.objects.get(pk=instance.pk)
            instance._old_date = old_instance.date
            instance._old_customer_id = old_instance.customer_id if old_instance.customer else None
            logger.debug(f"📝 Pre-save: Saved old date {instance._old_date} and customer {instance._old_customer_id}")
        except DailySaleTransaction.DoesNotExist:
            instance._old_date = None
            instance._old_customer_id = None
    else:
        instance._old_date = None
        instance._old_customer_id = None

@receiver(post_save, sender=DailySaleTransaction)
def dst_post_save(sender, instance, created, **kwargs):
    """
    بعد از ذخیره تراکنش، خلاصه‌ها را به‌روزرسانی کن
    """
    logger.info(f"💾 Transaction {'created' if created else 'updated'}: {instance.invoice_number}")
    
    try:
        # لیست تاریخ‌هایی که باید به‌روزرسانی شوند
        dates_to_update = set()
        
        # تاریخ جدید
        if instance.date:
            dates_to_update.add(instance.date)
        
        # تاریخ قدیم (اگر تغییر کرده)
        old_date = getattr(instance, '_old_date', None)
        if old_date and old_date != instance.date:
            dates_to_update.add(old_date)
        
        # به‌روزرسانی خلاصه برای هر تاریخ
        for d in dates_to_update:
            recompute_daily_summary_for_date(d)
        
        # به‌روزرسانی وضعیت مشتری
        customer_ids_to_update = set()
        
        # مشتری جدید
        if instance.customer_id:
            customer_ids_to_update.add(instance.customer_id)
        
        # مشتری قدیم (اگر تغییر کرده)
        old_customer_id = getattr(instance, '_old_customer_id', None)
        if old_customer_id and old_customer_id != instance.customer_id:
            customer_ids_to_update.add(old_customer_id)
        
        # به‌روزرسانی مانده هر مشتری
        for cid in customer_ids_to_update:
            recompute_outstanding_for_customer(cid)
        
        logger.info(f"✅ Post-save processing completed for {instance.invoice_number}")
        
    except Exception as e:
        logger.error(f"❌ Error in dst_post_save for transaction {instance.invoice_number}: {str(e)}")
        # خطا را لاگ کن اما بالا نفرست تا عملیات ذخیره مختل نشود

@receiver(pre_delete, sender=DailySaleTransaction)
def dst_pre_delete(sender, instance, **kwargs):
    """
    قبل از حذف تراکنش، اطلاعات لازم را ذخیره کن
    """
    instance._delete_date = instance.date
    instance._delete_customer_id = instance.customer_id if instance.customer else None
    logger.info(f"🗑️ Preparing to delete transaction: {instance.invoice_number}")

@receiver(post_delete, sender=DailySaleTransaction)
def dst_post_delete(sender, instance, **kwargs):
    """
    بعد از حذف تراکنش، خلاصه‌ها را به‌روزرسانی کن
    """
    logger.info(f"🗑️ Transaction deleted: {instance.invoice_number}")
    
    try:
        # به‌روزرسانی خلاصه روزانه
        delete_date = getattr(instance, '_delete_date', None)
        if delete_date:
            recompute_daily_summary_for_date(delete_date)
        
        # به‌روزرسانی وضعیت مشتری
        delete_customer_id = getattr(instance, '_delete_customer_id', None)
        if delete_customer_id:
            recompute_outstanding_for_customer(delete_customer_id)
        
        logger.info(f"✅ Post-delete processing completed")
        
    except Exception as e:
        logger.error(f"❌ Error in dst_post_delete: {str(e)}")

@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    بعد از ذخیره پرداخت، خلاصه‌ها را به‌روزرسانی کن
    """
    logger.info(f"💰 Payment {'created' if created else 'updated'}: {instance.amount} for transaction {instance.transaction.invoice_number}")
    
    try:
        # به‌روزرسانی خلاصه روزانه
        if instance.transaction and instance.transaction.date:
            recompute_daily_summary_for_date(instance.transaction.date)
        
        # به‌روزرسانی وضعیت مشتری
        if instance.transaction and instance.transaction.customer_id:
            recompute_outstanding_for_customer(instance.transaction.customer_id)
        
        logger.info(f"✅ Payment post-save processing completed")
        
    except Exception as e:
        logger.error(f"❌ Error in payment_post_save: {str(e)}")

@receiver(post_delete, sender=Payment)
def payment_post_delete(sender, instance, **kwargs):
    """
    بعد از حذف پرداخت، خلاصه‌ها را به‌روزرسانی کن
    """
    logger.info(f"💰 Payment deleted: {instance.amount}")
    
    try:
        # به‌روزرسانی خلاصه روزانه
        if instance.transaction and instance.transaction.date:
            recompute_daily_summary_for_date(instance.transaction.date)
        
        # به‌روزرسانی وضعیت مشتری
        if instance.transaction and instance.transaction.customer_id:
            recompute_outstanding_for_customer(instance.transaction.customer_id)
        
        logger.info(f"✅ Payment post-delete processing completed")
        
    except Exception as e:
        logger.error(f"❌ Error in payment_post_delete: {str(e)}")

@receiver(post_save, sender=DailySummary)
def daily_summary_post_save(sender, instance, created, **kwargs):
    """
    لاگ خلاصه روزانه بعد از ذخیره
    """
    if created:
        logger.info(f"📊 New daily summary created for {instance.date}")
    else:
        logger.debug(f"📊 Daily summary updated for {instance.date}")

@receiver(post_save, sender=OutstandingCustomer)
def outstanding_post_save(sender, instance, created, **kwargs):
    """
    لاگ وضعیت بدهکار بعد از ذخیره
    """
    customer_name = getattr(instance.customer, 'user', instance.customer)
    if created:
        logger.info(f"👤 New outstanding record created for {customer_name}: {instance.total_debt}")
    else:
        logger.debug(f"👤 Outstanding updated for {customer_name}: {instance.total_debt}")