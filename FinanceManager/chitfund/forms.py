from django import forms
from django.core.exceptions import ValidationError

from .models import Client


class ClientForm(forms.ModelForm):
    def validate_unique(self):
        """
        Allow duplicate phone numbers even if stale schema metadata is cached.
        """
        exclude = self._get_validation_exclusions()
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
