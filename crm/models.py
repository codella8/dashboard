from django.db import models

# Create your models here.
class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    company = models.CharField(max_length=100, blank=True)
    national_id = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return self.name
