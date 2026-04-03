from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from .models import Client, DailyExpense


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
