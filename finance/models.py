from django.db import models

class ExchangeOffice(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=100, blank=True)
    
    def __str__(self):
        return self.name
    
class ExchangeTransaction(models.Model):
    date = models.DateField()
    direction = models.CharField(max_length=10, choices=[('in', 'In'), ('out', 'Out')])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_office = models.ForeignKey(ExchangeOffice, on_delete=models.CASCADE)
    container_no = models.CharField(max_length=50, blank=True)
    
    def __str__(self):
        return f"{self.direction} - {self.amount}"