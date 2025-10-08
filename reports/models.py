from django.db import models

class Report(models.Model):
    REPORT_TYPES = [
        ('sale', 'گزارش فروش'),
        ('expense', 'گزارش هزینه'),
        ('employee', 'گزارش کارمند'),
        ('container', 'گزارش کانتینر'),
        ('custom', 'گزارش سفارشی'),
    ]

    title = models.CharField(max_length=100)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} ({self.get_report_type_display()})"

class ReportEntry(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='entries')
    date = models.DateField()
    section = models.CharField(max_length=100)  # مثل "فروش روزانه"، "هزینه حمل‌ونقل"
    reference_id = models.CharField(max_length=50, blank=True)  # شناسه خارجی مثل شماره فاکتور یا کد کالا
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.section} – {self.amount} on {self.date}"

class ReportAttachment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='reports/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"Attachment for {self.report.title}"
