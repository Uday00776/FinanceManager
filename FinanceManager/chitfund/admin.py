from django.contrib import admin

from .models import Client, DailyExpense, MonthlyPayment


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "monthly_amount", "status", "lifted_month", "joined_date")
    list_filter = ("status", "joined_date")
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

# Register your models here.
