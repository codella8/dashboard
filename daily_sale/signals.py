from django.db.models.signals import post_save
from django.dispatch import receiver
from . models import DailySaleTransaction

@receiver(post_save, sender=DailySaleTransaction)
def update_daily_summary(sender, instance, created, **kwargs):
    if created:
        # اگر تراکنش جدید است، خلاصه روزانه را به‌روز می‌کنیم
        instance.update_daily_summary()
