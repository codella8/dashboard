import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator, EmailValidator

class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique registered name of the company"
    )
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(
        max_length=30,
        blank=True,
        db_index=True,
        validators=[RegexValidator(r'^[\d\+\-\s\(\)]+$', 'Invalid phone number format')],
    )
    email = models.EmailField(
        max_length=255,
        blank=True,
        validators=[EmailValidator(message="Enter a valid email address")],
    )
    address = models.TextField(blank=True)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self):
        return self.name

    @property
    def total_employees(self):
        """Counts active employees linked to this company."""
        return self.employees.filter(is_verified=True).count()

    @property
    def active_status(self):
        return "Active" if self.is_active else "Inactive"


class UserProfile(models.Model):
    ROLE_CUSTOMER = "customer"
    ROLE_EMPLOYEE = "employee"
    ROLE_SARAF = "saraf"
    ROLE_COMPANY = "company"

    ROLE_CHOICES = [
        (ROLE_CUSTOMER, "Customer"),
        (ROLE_EMPLOYEE, "Employee"),
        (ROLE_SARAF, "saraf"),
        (ROLE_COMPANY, "Company"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="User Account"
    )
    account = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_CUSTOMER,
        db_index=True,
        verbose_name="Account Type",
        help_text="Defines the user role and permissions in the system"
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_CUSTOMER,
        db_index=True,
        verbose_name="Role"
    )

    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(max_length=255, blank=True, db_index=True)
    phone = models.CharField(
        max_length=30,
        blank=True,
        db_index=True,
        validators=[RegexValidator(r'^[\d\+\-\s\(\)]+$', 'Invalid phone number format')],
    )
    address = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    national_id = models.CharField(max_length=50, blank=True, unique=False)
    state = models.CharField(max_length=100, blank=True)
    zipcode = models.CharField(max_length=20, blank=True)

    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Company"
    )

    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account"]),
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user"], name="unique_user_profile")
        ]

    def __str__(self):
        return f"{self.full_name or self.user.username} – {self.get_account_display()}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.user.get_full_name()

    @property
    def short_name(self):
        return self.first_name or self.user.username

    @property
    def company_name(self):
        return self.company.name if self.company else "No company assigned"

    def mark_verified(self):
        """Mark the profile as verified and save."""
        self.is_verified = True
        self.save(update_fields=["is_verified", "updated_at"])

    def deactivate(self):
        """Soft deactivate the user profile."""
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])
        
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_staff_or_admin(self):
        return self.role in [self.ROLE_EMPLOYEE, self.ROLE_ADMIN]
