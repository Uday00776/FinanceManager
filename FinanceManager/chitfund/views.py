from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ClientForm
from .models import Client, MonthlyPayment


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


def dashboard(request):
    selected_month = _parse_month(request.GET.get("month"))
    active_clients = Client.objects.filter(is_active=True)

    for client in active_clients:
        MonthlyPayment.objects.get_or_create(
            client=client,
            month=selected_month,
            defaults={"status": MonthlyPayment.PaymentStatus.UNPAID, "amount_paid": 0},
        )

    payments = MonthlyPayment.objects.filter(
        month=selected_month, client__is_active=True
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
    expected_amount = active_clients.aggregate(total=Sum("monthly_amount"))["total"] or Decimal("0")
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


def client_list(request):
    clients = Client.objects.all()
    query = request.GET.get("q")
    sort_by = request.GET.get("sort_by", "name")
    sort_order = request.GET.get("sort_order", "asc")

    allowed_sort_fields = {
        "name": "name",
        "phone": "phone",
        "monthly_amount": "monthly_amount",
        "is_active": "is_active",
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


def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Client added successfully.")
            return redirect("client-list")
    else:
        form = ClientForm()
    return render(request, "chitfund/client_form.html", {"form": form, "title": "Add Client"})


def client_edit(request, client_id):
    client = get_object_or_404(Client, id=client_id)
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
def toggle_payment_status(request, payment_id):
    payment = get_object_or_404(MonthlyPayment, id=payment_id)
    if payment.status == MonthlyPayment.PaymentStatus.PAID:
        payment.status = MonthlyPayment.PaymentStatus.UNPAID
        payment.amount_paid = 0
        payment.paid_date = None
    else:
        payment.status = MonthlyPayment.PaymentStatus.PAID
        payment.amount_paid = payment.client.monthly_amount
        payment.paid_date = date.today()
    payment.save()
    return redirect(f"{request.META.get('HTTP_REFERER', '/')}")

# Create your views here.
