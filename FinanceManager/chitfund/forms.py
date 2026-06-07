from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import (
    Client,
    CreditFriend,
    CreditTransaction,
    DailyExpense,
    DailyFinanceClient,
    DailyFinancePayment,
)


class ClientForm(forms.ModelForm):
    def validate_unique(self):
        """
        Allow duplicate phone numbers even if stale schema metadata is cached.
        """
        if getattr(self, "_errors", None) is None:
            # Requires full_clean/is_valid to be called first to populate _errors
            return

        exclude = self._get_validation_exclusions()
        if "phone" not in exclude:
            exclude.add("phone")
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as exc:
            self._update_errors(exc)

    class Meta:
        model = Client
        fields = ["name", "phone", "address", "monthly_amount", "status", "lifted_month"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "lifted_month": forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lifted_month"].input_formats = ["%Y-%m", "%Y-%m-%d"]

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        lifted_month = cleaned_data.get("lifted_month")

        if status == Client.LiftStatus.LIFTED and not lifted_month:
            self.add_error("lifted_month", "Lifting month is required for lifted clients.")
        if status == Client.LiftStatus.NOT_LIFTED:
            cleaned_data["lifted_month"] = None
        return cleaned_data


class MonthSelectionForm(forms.Form):
    month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}),
    )


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class EmailOrUsernameAuthenticationForm(forms.Form):
    username = forms.CharField(label="Username or Email")
    password = forms.CharField(widget=forms.PasswordInput)

    error_messages = {
        "invalid_login": "Please enter a correct username/email and password.",
        "inactive": "This account is inactive.",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username_input = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username_input and password:
            lookup_username = username_input
            if "@" in username_input:
                user = User.objects.filter(email__iexact=username_input).first()
                if user:
                    lookup_username = user.username
            self.user_cache = authenticate(
                self.request, username=lookup_username, password=password
            )
            if self.user_cache is None:
                raise ValidationError(
                    self.error_messages["invalid_login"], code="invalid_login"
                )
            if not self.user_cache.is_active:
                raise ValidationError(self.error_messages["inactive"], code="inactive")
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class DailyExpenseForm(forms.ModelForm):
    class Meta:
        model = DailyExpense
        fields = ["expense_date", "category", "description", "amount"]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }


class CreditFriendForm(forms.ModelForm):
    class Meta:
        model = CreditFriend
        fields = ["name", "phone", "email", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class CreditTransactionForm(forms.ModelForm):
    class Meta:
        model = CreditTransaction
        fields = ["amount", "transaction_type", "date", "description"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.TextInput(attrs={"placeholder": "e.g. lunch, gpay, coffee"}),
        }


class DailyFinanceClientForm(forms.ModelForm):
    MONEY_PLACES = Decimal("0.01")

    class Meta:
        model = DailyFinanceClient
        fields = [
            "name",
            "phone",
            "address",
            "asked_amount",
            "interest_rate_percent",
            "duration_days",
            "interest_amount",
            "given_amount",
            "daily_installment",
            "start_date",
            "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "asked_amount": forms.NumberInput(attrs={"min": "1", "step": "0.01"}),
            "interest_rate_percent": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "duration_days": forms.NumberInput(attrs={"min": "1"}),
            "interest_amount": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "given_amount": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "daily_installment": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["interest_amount"].required = False
        self.fields["given_amount"].required = False
        self.fields["daily_installment"].required = False
        self.fields["start_date"].label = "Loan Date"
        self.fields["start_date"].help_text = "Collections start from the next day."
        self.fields["interest_rate_percent"].help_text = "Monthly interest rate. For 100 days, 5% becomes 15% total pre-deducted interest."
        self.fields["duration_days"].help_text = "Default is 100 days. The daily installment is asked amount divided by this duration."

    def clean(self):
        cleaned_data = super().clean()
        asked_amount = cleaned_data.get("asked_amount")
        interest_rate_percent = cleaned_data.get("interest_rate_percent") or Decimal("5.00")
        duration_days = cleaned_data.get("duration_days") or 100

        if asked_amount is not None and asked_amount <= 0:
            self.add_error("asked_amount", "Asked amount must be greater than zero.")
        if interest_rate_percent < 0:
            self.add_error("interest_rate_percent", "Interest rate cannot be negative.")
        if duration_days <= 0:
            self.add_error("duration_days", "Duration must be at least one day.")

        if asked_amount and duration_days > 0:
            duration = Decimal(duration_days)
            monthly_equivalent = duration * Decimal("3") / Decimal("100")
            default_interest = (
                asked_amount
                * (interest_rate_percent / Decimal("100"))
                * monthly_equivalent
            ).quantize(self.MONEY_PLACES, rounding=ROUND_HALF_UP)
            
            if cleaned_data.get("interest_amount") is None:
                cleaned_data["interest_amount"] = default_interest
            
            interest_amount = cleaned_data["interest_amount"]
            if interest_amount is not None and interest_amount < 0:
                self.add_error("interest_amount", "Interest amount cannot be negative.")
            elif interest_amount is not None and interest_amount >= asked_amount:
                self.add_error("interest_amount", "Interest amount must be less than asked amount.")
            
            if cleaned_data.get("given_amount") is None and interest_amount is not None:
                cleaned_data["given_amount"] = (asked_amount - interest_amount).quantize(
                    self.MONEY_PLACES,
                    rounding=ROUND_HALF_UP,
                )
                
            if cleaned_data.get("daily_installment") is None:
                cleaned_data["daily_installment"] = (asked_amount / duration).quantize(
                    self.MONEY_PLACES,
                    rounding=ROUND_HALF_UP,
                )

        return cleaned_data


class DailyFinancePaymentForm(forms.ModelForm):
    class Meta:
        model = DailyFinancePayment
        fields = ["date", "amount_paid", "status", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.TextInput(attrs={"placeholder": "Optional notes"}),
        }
