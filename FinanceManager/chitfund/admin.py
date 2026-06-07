from django.contrib import admin

from .models import (
    Client,
    DailyExpense,
    DailyFinanceClient,
    DailyFinancePayment,
    MonthlyPayment,
)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "chit_fund",
        "monthly_amount",
        "status",
        "lifted_month",
        "joined_date",
    )
    list_filter = ("chit_fund", "status", "joined_date")
    search_fields = ("name", "phone")


@admin.register(MonthlyPayment)
class MonthlyPaymentAdmin(admin.ModelAdmin):
    list_display = ("client", "month", "status", "amount_paid", "paid_date")
    list_filter = ("status", "month")
    search_fields = ("client__name", "client__phone")


@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ("user", "expense_date", "category", "amount")
    list_filter = ("expense_date", "category")
    search_fields = ("user__username", "category", "description")


@admin.register(DailyFinanceClient)
class DailyFinanceClientAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "asked_amount",
        "given_amount",
        "daily_installment",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = ("is_active", "start_date")
    search_fields = ("name", "phone", "user__username")


@admin.register(DailyFinancePayment)
class DailyFinancePaymentAdmin(admin.ModelAdmin):
    list_display = ("client", "date", "status", "amount_paid")
    list_filter = ("status", "date")
    search_fields = ("client__name", "client__phone")
