from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Client(models.Model):
    class LiftStatus(models.TextChoices):
        NOT_LIFTED = "NOT_LIFTED", "Not Lifted"
        LIFTED = "LIFTED", "Lifted"

    class ChitFund(models.TextChoices):
        FIVE_LAKH = "FIVE_LAKH", "5 lakh chitti"
        TWO_LAKH = "TWO_LAKH", "2 lakh chitti"
        NEW_TWO_LAKH = "NEW_TWO_LAKH", "new 2 lakh chitti"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="clients", default=1)
    chit_fund = models.CharField(
        max_length=20,
        choices=ChitFund.choices,
        default=ChitFund.TWO_LAKH,
    )

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
    class Category(models.TextChoices):
        PERSONAL = "PERSONAL", "Personal expenses"
        HOME = "HOME", "Home expenses"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_expenses")
    expense_date = models.DateField(default=timezone.localdate)
    category = models.CharField(
        max_length=80,
        choices=Category.choices,
        default=Category.PERSONAL,
    )
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.expense_date} - {self.category} - {self.amount}"


class CreditFriend(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="credit_friends")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = ["user", "name"]

    def __str__(self):
        return self.name


class CreditTransaction(models.Model):
    class TransactionType(models.TextChoices):
        GIVE = "GIVE", "Lent"
        RECEIVE = "RECEIVE", "Returned"

    friend = models.ForeignKey(CreditFriend, on_delete=models.CASCADE, related_name="transactions")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        default=TransactionType.GIVE,
    )
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.friend.name} - {self.get_transaction_type_display()} - Rs. {self.amount}"


class DailyFinanceClient(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="daily_finance_clients")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    
    asked_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total amount requested by the client (e.g. 100,000)")
    interest_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5.00, help_text="Monthly interest rate (e.g. 5%)")
    duration_days = models.IntegerField(default=100, help_text="Duration of the loan in days")
    
    interest_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Pre-deducted interest amount")
    given_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Actual amount given to client (asked_amount - interest_amount)")
    daily_installment = models.DecimalField(max_digits=10, decimal_places=2, help_text="Daily installment amount (asked_amount / duration_days)")
    
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(help_text="Expected completion date")
    is_active = models.BooleanField(default=True, help_text="Is the loan currently active?")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]

    def __str__(self):
        return f"{self.name} - Rs. {self.asked_amount}"


class DailyFinancePayment(models.Model):
    class PaymentStatus(models.TextChoices):
        PAID = "PAID", "Paid"
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partial"

    client = models.ForeignKey(DailyFinanceClient, on_delete=models.CASCADE, related_name="payments")
    date = models.DateField()
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PAID,
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        unique_together = ["client", "date"]

    def __str__(self):
        return f"{self.client.name} - {self.date} - Rs. {self.amount_paid} ({self.status})"
