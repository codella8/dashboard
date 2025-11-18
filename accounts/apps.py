from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    
    def ready(self): # این متد برای لود کردن فایل های سیگنال ها به کار میرود
        import accounts.signals
