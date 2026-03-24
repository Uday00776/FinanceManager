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
        fields = ["name", "phone", "address", "monthly_amount", "is_active"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


class MonthSelectionForm(forms.Form):
    month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(attrs={"type": "month"}),
    )
