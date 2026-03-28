from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Client(models.Model):
    class LiftStatus(models.TextChoices):
        NOT_LIFTED = "NOT_LIFTED", "Not Lifted"
        LIFTED = "LIFTED", "Lifted"

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    status = models.CharField(
        max_length=20, choices=LiftStatus.choices, default=LiftStatus.NOT_LIFTED
    )
    lifted_month = models.DateField(
        null=True,
        blank=True,
        help_text="Set as first day of month. Example: 2026-03-01.",
    )
    joined_date = models.DateField(default=timezone.localdate)
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.phone})"


class MonthlyPayment(models.Model):
    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        UNPAID = "UNPAID", "Unpaid"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="payments")
    month = models.DateField(
        help_text="Use the first day of month. Example: 2026-03-01 for March 2026."
    )
    status = models.CharField(
        max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "client__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "month"], name="unique_client_month_payment"
            )
        ]

    def __str__(self):
        return f"{self.client.name} - {self.month:%Y-%m} - {self.status}"


class DailyExpense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_expenses")
    expense_date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.expense_date} - {self.category} - {self.amount}"
