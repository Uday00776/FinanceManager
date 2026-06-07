from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.db.models import Count, Max, Q, Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    ClientForm,
    DailyExpenseForm,
    EmailOrUsernameAuthenticationForm,
    SignUpForm,
    CreditFriendForm,
    CreditTransactionForm,
    DailyFinanceClientForm,
    DailyFinancePaymentForm,
)
from .models import (
    Client,
    DailyExpense,
    MonthlyPayment,
    CreditFriend,
    CreditTransaction,
    DailyFinanceClient,
    DailyFinancePayment,
)
from chitfund.ml.risk_predictor import risk_predictor


CHIT_FUNDS = [
    {
        "slug": "5-lakh-chitti",
        "key": Client.ChitFund.FIVE_LAKH,
        "name": "5 lakh chitti",
        "description": "Track members and monthly collections for the 5 lakh chit.",
        "accent": "indigo",
    },
    {
        "slug": "2-lakh-chitti",
        "key": Client.ChitFund.TWO_LAKH,
        "name": "2 lakh chitti",
        "description": "Existing client details and payment history are kept here.",
        "accent": "green",
    },
    {
        "slug": "new-2-lakh-chitti",
        "key": Client.ChitFund.NEW_TWO_LAKH,
        "name": "new 2 lakh chitti",
        "description": "Start the new 2 lakh chit with a fresh client and payment list.",
        "accent": "orange",
    },
]


def _funds_by_slug():
    return {fund["slug"]: fund for fund in CHIT_FUNDS}


def _get_chit_fund(fund_slug):
    try:
        return _funds_by_slug()[fund_slug]
    except KeyError as exc:
        raise Http404("Chit fund not found.") from exc


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


def _local_today():
    return timezone.localdate()


def _parse_selected_date(request):
    raw = request.GET.get("date") or request.POST.get("date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return _local_today()


def _daily_finance_redirect_url(request, selected_date=None):
    selected_date = selected_date or _parse_selected_date(request)
    params = []
    query = request.GET.get("q") or request.POST.get("q")
    if query:
        params.append(f"q={query}")
    if request.GET.get("completed") == "true" or request.POST.get("completed") == "true":
        params.append("completed=true")
    if selected_date != _local_today():
        params.append(f"date={selected_date.isoformat()}")
    if not params:
        return "/daily-finance/"
    return f"/daily-finance/?{'&'.join(params)}"


def _daily_finance_collection_start(client):
    return client.start_date + timedelta(days=1)


def _daily_finance_planned_end(client):
    return client.start_date + timedelta(days=client.duration_days)


def _payable_amount_for_month(client, payment_month):
    if client.chit_fund == Client.ChitFund.NEW_TWO_LAKH:
        return client.monthly_amount
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
def chitfund_management(request):
    return render(request, "chitfund/chitfund_management.html", {"chit_funds": CHIT_FUNDS})


@login_required
def dashboard(request, fund_slug):
    chit_fund = _get_chit_fund(fund_slug)
    selected_month = _parse_month(request.GET.get("month"))
    clients = Client.objects.filter(user=request.user, chit_fund=chit_fund["key"]).filter(
        Q(joined_date__year__lt=selected_month.year) |
        Q(joined_date__year=selected_month.year, joined_date__month__lte=selected_month.month)
    )

    existing_payments = MonthlyPayment.objects.filter(
        month=selected_month, client__user=request.user, client__chit_fund=chit_fund["key"]
    )
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
    for payment in payments:
        payment.payable_amount = _payable_amount_for_month(payment.client, selected_month)

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
        (payment.payable_amount for payment in payments),
        start=Decimal("0"),
    )
    pending_amount = expected_amount - total_collected

    # AI Risk insights
    high_risk_count = 0
    for client in clients:
        risk_info = risk_predictor.predict_risk(client.id)
        if risk_info.get("level") == "High":
            high_risk_count += 1

    context = {
        "selected_month": selected_month,
        "payments": payments,
        "total_clients": total_clients,
        "paid_clients": paid_clients,
        "unpaid_clients": unpaid_clients,
        "total_collected": total_collected,
        "pending_amount": pending_amount,
        "expected_amount": expected_amount,
        "high_risk_count": high_risk_count,
        "chit_fund": chit_fund,
    }
    return render(request, "chitfund/dashboard.html", context)


@login_required
def client_list(request, fund_slug):
    chit_fund = _get_chit_fund(fund_slug)
    clients = Client.objects.filter(user=request.user, chit_fund=chit_fund["key"])
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
    clients = list(clients.order_by(sort_field))

    # Add AI Risk predictions
    for client in clients:
        client.risk = risk_predictor.predict_risk(client.id)

    return render(
        request,
        "chitfund/client_list.html",
        {
            "clients": clients,
            "query": query or "",
            "sort_by": sort_by,
            "sort_order": sort_order,
            "chit_fund": chit_fund,
        },
    )


@login_required
def client_create(request, fund_slug):
    chit_fund = _get_chit_fund(fund_slug)
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.user = request.user
            client.chit_fund = chit_fund["key"]
            client.save()
            messages.success(request, "Client added successfully.")
            return redirect("client-list", fund_slug=fund_slug)
    else:
        form = ClientForm()
    return render(
        request,
        "chitfund/client_form.html",
        {"form": form, "title": "Add Client", "chit_fund": chit_fund},
    )


@login_required
def client_edit(request, fund_slug, client_id):
    chit_fund = _get_chit_fund(fund_slug)
    client = get_object_or_404(
        Client, id=client_id, user=request.user, chit_fund=chit_fund["key"]
    )
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, "Client updated successfully.")
            return redirect("client-list", fund_slug=fund_slug)
    else:
        form = ClientForm(instance=client)
    return render(
        request,
        "chitfund/client_form.html",
        {"form": form, "title": "Edit Client", "chit_fund": chit_fund},
    )


@login_required
def legacy_client_list_redirect(request):
    return redirect("client-list", fund_slug="2-lakh-chitti")


@login_required
def legacy_client_create_redirect(request):
    return redirect("client-create", fund_slug="2-lakh-chitti")


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
    stats = expenses.aggregate(
        total=Sum("amount"),
        personal=Sum("amount", filter=Q(category=DailyExpense.Category.PERSONAL)),
        home=Sum("amount", filter=Q(category=DailyExpense.Category.HOME)),
    )
    total_expense = stats["total"] or Decimal("0")
    personal_expense = stats["personal"] or Decimal("0")
    home_expense = stats["home"] or Decimal("0")

    context = {
        "expenses": expenses,
        "selected_month": month,
        "total_expense": total_expense,
        "personal_expense": personal_expense,
        "home_expense": home_expense,
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


@login_required
def credits_dashboard(request, friend_id=None):
    # Query all friends for the current user and calculate their balances
    friends = CreditFriend.objects.filter(user=request.user).annotate(
        total_lent=Coalesce(
            Sum(
                "transactions__amount",
                filter=Q(transactions__transaction_type="GIVE"),
            ),
            Decimal("0.0"),
            output_field=DecimalField(),
        ),
        total_returned=Coalesce(
            Sum(
                "transactions__amount",
                filter=Q(transactions__transaction_type="RECEIVE"),
            ),
            Decimal("0.0"),
            output_field=DecimalField(),
        ),
    ).annotate(
        balance=F("total_lent") - F("total_returned")
    ).order_by("-balance", "name")

    # Calculate global stats (only summing positive balances where they owe us money)
    total_receivables = Decimal("0.0")
    active_debtors_count = 0
    for f in friends:
        if f.balance > 0:
            total_receivables += f.balance
            active_debtors_count += 1

    selected_friend = None
    transactions = []
    friend_balance = Decimal("0.0")
    
    friend_form = CreditFriendForm()
    transaction_form = CreditTransactionForm()

    if friend_id:
        selected_friend = get_object_or_404(CreditFriend, id=friend_id, user=request.user)
        # Fetch transactions for this friend
        transactions = selected_friend.transactions.all()
        # Calculate selected friend's balance
        lent = transactions.filter(transaction_type="GIVE").aggregate(Sum("amount"))["amount__sum"] or Decimal("0.0")
        returned = transactions.filter(transaction_type="RECEIVE").aggregate(Sum("amount"))["amount__sum"] or Decimal("0.0")
        friend_balance = lent - returned
    else:
        # If no friend selected, get the last 10 transactions overall for this user
        transactions = CreditTransaction.objects.filter(friend__user=request.user).select_related("friend")[:10]

    context = {
        "friends": friends,
        "selected_friend": selected_friend,
        "transactions": transactions,
        "friend_balance": friend_balance,
        "total_receivables": total_receivables,
        "active_debtors_count": active_debtors_count,
        "friend_form": friend_form,
        "transaction_form": transaction_form,
    }
    return render(request, "chitfund/credits/dashboard.html", context)


@login_required
@require_POST
def add_friend(request):
    form = CreditFriendForm(request.POST)
    if form.is_valid():
        friend = form.save(commit=False)
        friend.user = request.user
        friend.save()
        messages.success(request, f"Friend '{friend.name}' added successfully.")
        return redirect("credits-detail", friend_id=friend.id)
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.capitalize()}: {error}")
    return redirect("credits-dashboard")


@login_required
@require_POST
def add_transaction(request, friend_id):
    friend = get_object_or_404(CreditFriend, id=friend_id, user=request.user)
    form = CreditTransactionForm(request.POST)
    if form.is_valid():
        transaction = form.save(commit=False)
        transaction.friend = friend
        transaction.save()
        
        type_str = "Lent" if transaction.transaction_type == "GIVE" else "Returned"
        messages.success(
            request, 
            f"Recorded Rs. {transaction.amount} as {type_str} for {friend.name}."
        )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"Error: {error}")
    return redirect("credits-detail", friend_id=friend.id)


@login_required
def delete_friend(request, friend_id):
    friend = get_object_or_404(CreditFriend, id=friend_id, user=request.user)
    name = friend.name
    friend.delete()
    messages.success(request, f"Friend '{name}' and all their transactions deleted.")
    return redirect("credits-dashboard")


@login_required
def delete_transaction(request, transaction_id):
    transaction = get_object_or_404(CreditTransaction, id=transaction_id, friend__user=request.user)
    friend_id = transaction.friend.id
    amount = transaction.amount
    type_str = "Lent" if transaction.transaction_type == "GIVE" else "Returned"
    transaction.delete()
    messages.success(request, f"Deleted {type_str} transaction of Rs. {amount}.")
    return redirect("credits-detail", friend_id=friend_id)


# ==============================================================================
# Daily Finance Tracker Views
# ==============================================================================

@login_required
def daily_finance_dashboard(request):
    query = request.GET.get("q")
    show_completed = request.GET.get("completed") == "true"
    selected_date = _parse_selected_date(request)
    local_today = _local_today()
    is_viewing_today = selected_date == local_today
    is_future_date = selected_date > local_today
    
    clients = DailyFinanceClient.objects.filter(user=request.user)
    if query:
        clients = clients.filter(Q(name__icontains=query) | Q(phone__icontains=query))
    
    # Pre-fetch payments count for each client to calculate progress
    active_clients = clients.filter(is_active=True)
    completed_clients = clients.filter(is_active=False)
    
    # Calculate global stats across all active loans
    stats = active_clients.aggregate(
        total_asked=Sum("asked_amount"),
        total_given=Sum("given_amount"),
        total_interest=Sum("interest_amount"),
    )
    
    total_asked = stats["total_asked"] or Decimal("0.00")
    total_given = stats["total_given"] or Decimal("0.00")
    total_interest = stats["total_interest"] or Decimal("0.00")
    
    collection_statuses = [
        DailyFinancePayment.PaymentStatus.PAID,
        DailyFinancePayment.PaymentStatus.PARTIAL,
    ]

    # Total collected across all active clients
    total_collected = DailyFinancePayment.objects.filter(
        client__user=request.user,
        client__is_active=True,
        status__in=collection_statuses,
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")
    
    total_remaining = total_asked - total_collected
    
    # Selected day's collections stats
    day_payments = DailyFinancePayment.objects.filter(
        client__user=request.user,
        client__is_active=True,
        date=selected_date,
    )
    day_collected_payments = day_payments.filter(status__in=collection_statuses)
    day_paid_client_ids = set(day_collected_payments.values_list("client_id", flat=True))
    day_payment_map = {p.client_id: p for p in day_payments}
    
    collectable_day_clients = [
        c for c in active_clients if _daily_finance_collection_start(c) <= selected_date
    ]
    day_expected = sum((c.daily_installment for c in collectable_day_clients), start=Decimal("0.00"))
    day_collected = day_collected_payments.aggregate(
        total=Sum("amount_paid")
    )["total"] or Decimal("0.00")
    
    # Process client list with calculated stats
    display_clients = []
    target_clients = completed_clients if show_completed else active_clients
    
    for c in target_clients:
        payments = c.payments.filter(status__in=collection_statuses)
        paid_count = payments.count()
        amt_paid = payments.aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")
        
        collection_started = _daily_finance_collection_start(c) <= selected_date
        selected_day_payment = day_payment_map.get(c.id) if not show_completed else None
        selected_day_status = (
            selected_day_payment.status
            if selected_day_payment
            else DailyFinancePayment.PaymentStatus.UNPAID
        )
        selected_day_amount = (
            selected_day_payment.amount_paid
            if selected_day_payment
            else Decimal("0.00")
        )
        progress_pct = (amt_paid / c.asked_amount) * 100 if c.asked_amount > 0 else 0
        progress_pct = min(progress_pct, Decimal("100.0"))
        
        display_clients.append({
            "client": c,
            "paid_days": paid_count,
            "amount_paid": amt_paid,
            "remaining_amount": c.asked_amount - amt_paid,
            "progress_percent": round(progress_pct, 1),
            "collection_started": collection_started,
            "selected_day_status": selected_day_status,
            "selected_day_amount": selected_day_amount,
        })
    
    context = {
        "clients": display_clients,
        "show_completed": show_completed,
        "query": query or "",
        "total_asked": total_asked,
        "total_given": total_given,
        "total_interest": total_interest,
        "total_collected": total_collected,
        "total_remaining": total_remaining,
        "selected_date": selected_date,
        "local_today": local_today,
        "is_viewing_today": is_viewing_today,
        "is_future_date": is_future_date,
        "day_expected": day_expected,
        "day_collected": day_collected,
        "day_paid_count": len(day_paid_client_ids),
        "total_active_count": active_clients.count(),
    }
    
    return render(request, "chitfund/daily_finance/dashboard.html", context)


@login_required
def daily_finance_client_detail(request, client_id):
    client = get_object_or_404(DailyFinanceClient, id=client_id, user=request.user)
    
    collection_statuses = [
        DailyFinancePayment.PaymentStatus.PAID,
        DailyFinancePayment.PaymentStatus.PARTIAL,
    ]

    # Load all payments for this client
    db_payments = list(client.payments.all())
    payment_map = {p.date: p for p in db_payments}
    
    total_paid = sum(
        (p.amount_paid for p in db_payments if p.status in collection_statuses),
        start=Decimal("0.00"),
    )
    remaining_balance = client.asked_amount - total_paid

    # Generate the original schedule, then extend it when collections continue.
    days = []
    start = _daily_finance_collection_start(client)
    today = _local_today()
    scheduled_days = max(client.duration_days, 1)
    elapsed_days = (today - start).days + 1 if today >= start else 0
    latest_payment_date = max((p.date for p in db_payments), default=None)
    latest_payment_day = (
        (latest_payment_date - start).days + 1
        if latest_payment_date and latest_payment_date >= start
        else 0
    )

    if client.is_active and remaining_balance > 0:
        ledger_days = max(scheduled_days, elapsed_days, latest_payment_day)
    else:
        ledger_days = max(scheduled_days, latest_payment_day)
    
    paid_days_count = 0
    missed_days_count = 0
    
    for i in range(ledger_days):
        day_date = start + timedelta(days=i)
        payment = payment_map.get(day_date)
        
        # Determine status
        if payment:
            status = payment.status
            amt = payment.amount_paid
            notes = payment.notes
            if status == DailyFinancePayment.PaymentStatus.PAID:
                paid_days_count += 1
        else:
            amt = Decimal("0.00")
            notes = ""
            if day_date < today:
                status = "MISSED"
                missed_days_count += 1
            else:
                status = "FUTURE"
        
        days.append({
            "day_number": i + 1,
            "date": day_date,
            "status": status,
            "amount_paid": amt,
            "notes": notes,
        })
        
    progress_pct = (total_paid / client.asked_amount) * 100 if client.asked_amount > 0 else 0
    progress_pct = min(progress_pct, Decimal("100.0"))
    
    # Determine general client financial health status
    scheduled_elapsed = max(0, min(elapsed_days, scheduled_days))
    expected_by_today = min(
        client.asked_amount,
        client.daily_installment * Decimal(scheduled_elapsed),
    )
    
    if client.is_active:
        if remaining_balance <= 0:
            health_status = "Fully Paid (Complete)"
            health_color = "green"
        elif total_paid >= expected_by_today:
            health_status = "On Track"
            health_color = "indigo"
        elif total_paid >= max(Decimal("0.00"), expected_by_today - (client.daily_installment * Decimal("2"))):
            health_status = "Slightly Behind"
            health_color = "yellow"
        else:
            health_status = "Critical (Behind)"
            health_color = "red"
    else:
        health_status = "Completed"
        health_color = "gray"
        
    context = {
        "client": client,
        "days": days,
        "total_paid": total_paid,
        "remaining_balance": remaining_balance,
        "paid_days_count": paid_days_count,
        "missed_days_count": missed_days_count,
        "progress_percent": round(progress_pct, 1),
        "health_status": health_status,
        "health_color": health_color,
        "days_elapsed": elapsed_days,
        "scheduled_days": scheduled_days,
        "ledger_days": ledger_days,
        "collection_start_date": start,
        "today": today,
    }
    
    return render(request, "chitfund/daily_finance/client_detail.html", context)


@login_required
def daily_finance_client_create(request):
    if request.method == "POST":
        form = DailyFinanceClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.user = request.user
            # Collections begin the day after the loan date.
            client.end_date = _daily_finance_planned_end(client)
            client.save()
            messages.success(request, f"Daily Finance Client '{client.name}' added successfully.")
            return redirect("daily-finance-dashboard")
    else:
        form = DailyFinanceClientForm(initial={
            "start_date": _local_today(),
            "interest_rate_percent": Decimal("5.00"),
            "duration_days": 100,
        })
        
    return render(request, "chitfund/daily_finance/client_form.html", {
        "form": form,
        "title": "Add Daily Finance Client",
    })


@login_required
def daily_finance_client_edit(request, client_id):
    client = get_object_or_404(DailyFinanceClient, id=client_id, user=request.user)
    if request.method == "POST":
        form = DailyFinanceClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save(commit=False)
            # Collections begin the day after the loan date.
            client.end_date = _daily_finance_planned_end(client)
            client.save()
            messages.success(request, f"Client '{client.name}' updated successfully.")
            return redirect("daily-finance-client-detail", client_id=client.id)
    else:
        form = DailyFinanceClientForm(instance=client)
        
    return render(request, "chitfund/daily_finance/client_form.html", {
        "form": form,
        "title": f"Edit Client: {client.name}",
    })


@login_required
def daily_finance_client_delete(request, client_id):
    client = get_object_or_404(DailyFinanceClient, id=client_id, user=request.user)
    name = client.name
    client.delete()
    messages.success(request, f"Daily Finance Client '{name}' and all payment logs deleted.")
    return redirect("daily-finance-dashboard")


@login_required
@require_POST
def daily_finance_toggle_today_payment(request, client_id):
    client = get_object_or_404(DailyFinanceClient, id=client_id, user=request.user)
    selected_date = _parse_selected_date(request)
    local_today = _local_today()
    requested_status = request.POST.get("status")

    if selected_date > local_today:
        messages.warning(request, "You cannot mark payments for a future date.")
        return redirect(_daily_finance_redirect_url(request, selected_date))

    if selected_date < _daily_finance_collection_start(client):
        messages.warning(request, "Collection starts from the day after the loan date.")
        return redirect(_daily_finance_redirect_url(request, selected_date))
    
    payment = DailyFinancePayment.objects.filter(client=client, date=selected_date).first()

    if requested_status:
        valid_statuses = {
            DailyFinancePayment.PaymentStatus.PAID,
            DailyFinancePayment.PaymentStatus.PARTIAL,
            DailyFinancePayment.PaymentStatus.UNPAID,
        }
        if requested_status not in valid_statuses:
            messages.warning(request, "Invalid payment status.")
            return redirect(_daily_finance_redirect_url(request, selected_date))

        if requested_status == DailyFinancePayment.PaymentStatus.UNPAID:
            if payment:
                payment.delete()
            return redirect(_daily_finance_redirect_url(request, selected_date))

        amount_str = request.POST.get("amount_paid")
        try:
            amount = Decimal(amount_str) if amount_str else client.daily_installment
        except (ValueError, TypeError):
            messages.warning(request, "Invalid payment amount.")
            return redirect(_daily_finance_redirect_url(request, selected_date))

        if amount < Decimal("0.00"):
            messages.warning(request, "Payment amount cannot be negative.")
            return redirect(_daily_finance_redirect_url(request, selected_date))

        if requested_status == DailyFinancePayment.PaymentStatus.PAID and not amount_str:
            amount = client.daily_installment

        if payment:
            payment.status = requested_status
            payment.amount_paid = amount
            payment.save()
        else:
            DailyFinancePayment.objects.create(
                client=client,
                date=selected_date,
                amount_paid=amount,
                status=requested_status,
            )

        return redirect(_daily_finance_redirect_url(request, selected_date))
    
    if payment:
        if payment.status == DailyFinancePayment.PaymentStatus.PAID:
            # Revert to unpaid (delete payment record)
            payment.delete()
            # If the loan was automatically marked inactive, reactivate it if needed
            # (though normally remains active until user changes status)
        else:
            # Mark paid
            payment.status = DailyFinancePayment.PaymentStatus.PAID
            payment.amount_paid = client.daily_installment
            payment.save()
    else:
        # Create paid payment record for today
        DailyFinancePayment.objects.create(
            client=client,
            date=selected_date,
            amount_paid=client.daily_installment,
            status=DailyFinancePayment.PaymentStatus.PAID,
        )
        
    return redirect(_daily_finance_redirect_url(request, selected_date))


@login_required
@require_POST
def daily_finance_update_day_payment(request, client_id):
    client = get_object_or_404(DailyFinanceClient, id=client_id, user=request.user)
    
    date_str = request.POST.get("date")
    amount_str = request.POST.get("amount_paid")
    status = request.POST.get("status")
    notes = request.POST.get("notes", "")
    
    try:
        payment_date = date.fromisoformat(date_str)
        amount = Decimal(amount_str) if amount_str else client.daily_installment
    except (ValueError, TypeError) as exc:
        messages.error(request, "Invalid payment values.")
        return redirect("daily-finance-client-detail", client_id=client.id)

    if payment_date < _daily_finance_collection_start(client):
        messages.error(request, "Collection starts from the day after the loan date.")
        return redirect("daily-finance-client-detail", client_id=client.id)
        
    payment, created = DailyFinancePayment.objects.get_or_create(
        client=client,
        date=payment_date,
        defaults={
            "amount_paid": amount,
            "status": status,
            "notes": notes,
        }
    )
    
    if not created:
        if status == "MISSED" or status == "FUTURE":
            # Deleting the record represents reverting to default unpaid/future state
            payment.delete()
        else:
            payment.amount_paid = amount
            payment.status = status
            payment.notes = notes
            payment.save()
            
    messages.success(request, f"Payment for {payment_date} updated.")
    return redirect("daily-finance-client-detail", client_id=client.id)
