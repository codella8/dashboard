# Minimal signals file. We don't create DailySummary/OldTransaction
# but we keep pre_save to store old values (useful if admin edits transaction)
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import DailySaleTransaction

@receiver(pre_save, sender=DailySaleTransaction)
def dst_pre_save(sender, instance, **kwargs):
    if not instance._state.adding:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_date = old.date
            instance._old_customer = getattr(old, 'customer_id', None)
        except sender.DoesNotExist:
            instance._old_date = None
            instance._old_customer = None
    else:
        instance._old_date = None
        instance._old_customer = None
