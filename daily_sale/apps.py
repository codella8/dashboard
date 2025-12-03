# daily_sale/apps.py
from django.apps import AppConfig


class DailySaleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'daily_sale'
    verbose_name = "Daily Sale"

    def ready(self):
        # ثبت سیگنال‌ها هنگام بارگذاری اپ
        from . import signals  # noqa: F401
