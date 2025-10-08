from django.db import models
from crm.models import Customer  # اگر صاحب کانتینر مشتری باشه

class Container(models.Model):
    code = models.CharField(max_length=50, unique=True)  # مثل شماره کانتینر یا پلاک ماشین
    type = models.CharField(max_length=50, blank=True)  # مثل کانتینر، وانت، کامیون
    owner = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    capacity = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # ظرفیت به تن یا متر مکعب
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return self.code
