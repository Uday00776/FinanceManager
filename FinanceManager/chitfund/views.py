from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    ClientForm,
    DailyExpenseForm,
    EmailOrUsernameAuthenticationForm,
    SignUpForm,
)
from .models import Client, DailyExpense, MonthlyPayment


def _first_day_of_current_month():
    today = date.today()
    return today.replace(day=1)


def _parse_month(month_param):
    if not month_param:
        return _first_day_of_current_month()
    try:
        year_str, month_str = month_param.split("-")
        return date(int(year_str), int(month_str), 1)
    except (ValueError, TypeError):
        return _first_day_of_current_month()


def _payable_amount_for_month(client, payment_month):
    if (
        client.status == Client.LiftStatus.LIFTED
        and client.lifted_month
        and payment_month > client.lifted_month
    ):
        return Decimal("12000")
    return client.monthly_amount


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = EmailOrUsernameAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("home")
    return render(request, "chitfund/auth/login.html", {"form": form})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created successfully.")
        return redirect("home")
    return render(request, "chitfund/auth/signup.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def home(request):
    return render(request, "chitfund/home.html")


@login_required
def dashboard(request):
    selected_month = _parse_month(request.GET.get("month"))
    clients = Client.objects.filter(user=request.user).filter(
        Q(joined_date__year__lt=selected_month.year) |
        Q(joined_date__year=selected_month.year, joined_date__month__lte=selected_month.month)
    )

    existing_payments = MonthlyPayment.objects.filter(month=selected_month)
    existing_client_ids = set(existing_payments.values_list('client_id', flat=True))

    missing_clients = [c for c in clients if c.id not in existing_client_ids]
    if missing_clients:
        MonthlyPayment.objects.bulk_create(
            [
                MonthlyPayment(
                    client=client,
                    month=selected_month,
                    status=MonthlyPayment.PaymentStatus.UNPAID,
                    amount_paid=0,
                )
                for client in missing_clients
            ]
        )

    payments = MonthlyPayment.objects.filter(
        month=selected_month, client__in=clients
    ).select_related("client")
    stats = payments.aggregate(
        total_clients=Count("id"),
        paid_clients=Count("id", filter=Q(status=MonthlyPayment.PaymentStatus.PAID)),
        unpaid_clients=Count("id", filter=Q(status=MonthlyPayment.PaymentStatus.UNPAID)),
        total_collected=Sum("amount_paid", filter=Q(status=MonthlyPayment.PaymentStatus.PAID)),
    )

    total_clients = stats["total_clients"] or 0
    paid_clients = stats["paid_clients"] or 0
    unpaid_clients = stats["unpaid_clients"] or 0
    total_collected = stats["total_collected"] or Decimal("0")
    expected_amount = sum(
        (_payable_amount_for_month(payment.client, selected_month) for payment in payments),
        start=Decimal("0"),
    )
    pending_amount = expected_amount - total_collected

    context = {
        "selected_month": selected_month,
        "payments": payments,
        "total_clients": total_clients,
        "paid_clients": paid_clients,
        "unpaid_clients": unpaid_clients,
        "total_collected": total_collected,
        "pending_amount": pending_amount,
        "expected_amount": expected_amount,
    }
    return render(request, "chitfund/dashboard.html", context)


@login_required
def client_list(request):
    clients = Client.objects.filter(user=request.user)
    query = request.GET.get("q")
    sort_by = request.GET.get("sort_by", "name")
    sort_order = request.GET.get("sort_order", "asc")

    allowed_sort_fields = {
        "name": "name",
        "phone": "phone",
        "monthly_amount": "monthly_amount",
        "status": "status",
        "lifted_month": "lifted_month",
        "joined_date": "joined_date",
    }
    sort_field = allowed_sort_fields.get(sort_by, "name")
    if sort_order == "desc":
        sort_field = f"-{sort_field}"

    if query:
        clients = clients.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    clients = clients.order_by(sort_field)

    return render(
        request,
        "chitfund/client_list.html",
        {
            "clients": clients,
            "query": query or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.user = request.user
            client.save()
            messages.success(request, "Client added successfully.")
            return redirect("client-list")
    else:
        form = ClientForm()
    return render(request, "chitfund/client_form.html", {"form": form, "title": "Add Client"})


@login_required
def client_edit(request, client_id):
    client = get_object_or_404(Client, id=client_id, user=request.user)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Client updated successfully.")
            return redirect("client-list")
    else:
        form = ClientForm(instance=client)
    return render(request, "chitfund/client_form.html", {"form": form, "title": "Edit Client"})


@require_POST
@login_required
def toggle_payment_status(request, payment_id):
    payment = get_object_or_404(MonthlyPayment, id=payment_id, client__user=request.user)
    payable_amount = _payable_amount_for_month(payment.client, payment.month)
    if payment.status == MonthlyPayment.PaymentStatus.PAID:
        payment.status = MonthlyPayment.PaymentStatus.UNPAID
        payment.amount_paid = 0
        payment.paid_date = None
    else:
        payment.status = MonthlyPayment.PaymentStatus.PAID
        payment.amount_paid = payable_amount
        payment.paid_date = date.today()
    payment.save()
    return redirect(f"{request.META.get('HTTP_REFERER', '/')}")


@login_required
def daily_expense_list(request):
    month = _parse_month(request.GET.get("month"))
    expenses = DailyExpense.objects.filter(
        user=request.user,
        expense_date__year=month.year,
        expense_date__month=month.month,
    )
    total_expense = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    context = {
        "expenses": expenses,
        "selected_month": month,
        "total_expense": total_expense,
    }
    return render(request, "chitfund/daily_expense_list.html", context)


@login_required
def daily_expense_create(request):
    form = DailyExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.user = request.user
        expense.save()
        messages.success(request, "Expense added successfully.")
        return redirect("daily-expense-list")
    return render(
        request,
        "chitfund/daily_expense_form.html",
        {"form": form, "title": "Add Daily Expense"},
    )
