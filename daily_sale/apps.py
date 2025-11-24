from django.apps import AppConfig


class DailySaleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'daily_sale'
    def ready(self): # این متد برای لود کردن فایل های سیگنال ها به کار میرود
        import daily_sale.signals
