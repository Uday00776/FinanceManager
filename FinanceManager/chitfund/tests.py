from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase, override_settings

from .forms import DailyFinanceClientForm
from .models import (
    CreditFriend,
    CreditTransaction,
    DailyFinanceClient,
    DailyFinancePayment,
)


class CreditTrackerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")

    def test_friend_creation_and_balance(self):
        friend = CreditFriend.objects.create(user=self.user, name="Alice")
        self.assertEqual(friend.name, "Alice")
        self.assertEqual(friend.transactions.count(), 0)

    def test_credit_transactions(self):
        friend = CreditFriend.objects.create(user=self.user, name="Bob")
        
        # Lent Bob some money
        CreditTransaction.objects.create(
            friend=friend,
            amount=Decimal("500.00"),
            transaction_type=CreditTransaction.TransactionType.GIVE,
            description="Lunch"
        )
        
        # Bob returned some money
        CreditTransaction.objects.create(
            friend=friend,
            amount=Decimal("200.00"),
            transaction_type=CreditTransaction.TransactionType.RECEIVE,
            description="GPay"
        )
        
        self.assertEqual(friend.transactions.count(), 2)
        
        # Test balance calculations
        lent = friend.transactions.filter(
            transaction_type=CreditTransaction.TransactionType.GIVE
        ).aggregate(sum=Sum('amount'))['sum'] or Decimal('0.0')
        
        returned = friend.transactions.filter(
            transaction_type=CreditTransaction.TransactionType.RECEIVE
        ).aggregate(sum=Sum('amount'))['sum'] or Decimal('0.0')
        
        balance = lent - returned
        self.assertEqual(balance, Decimal("300.00"))


class DailyFinanceTrackerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="financeuser", password="password")

    def test_client_form_calculates_default_100_day_terms(self):
        form = DailyFinanceClientForm(data={
            "name": "Ravi",
            "phone": "9999999999",
            "address": "Test address",
            "asked_amount": "100000",
            "interest_rate_percent": "5",
            "duration_days": "100",
            "start_date": "2026-06-02",
            "is_active": "on",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["interest_amount"], Decimal("15000.00"))
        self.assertEqual(form.cleaned_data["given_amount"], Decimal("85000.00"))
        self.assertEqual(form.cleaned_data["daily_installment"], Decimal("1000.00"))

    def test_create_page_renders_and_saves_daily_finance_client(self):
        self.client.login(username="financeuser", password="password")

        response = self.client.get("/daily-finance/add/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chitfund/daily_finance/client_form.html")

        response = self.client.post("/daily-finance/add/", {
            "name": "Sita",
            "phone": "8888888888",
            "address": "",
            "asked_amount": "100000",
            "interest_rate_percent": "5",
            "duration_days": "100",
            "start_date": "2026-06-02",
            "is_active": "on",
        })

        self.assertRedirects(response, "/daily-finance/")
        client = DailyFinanceClient.objects.get(user=self.user, name="Sita")
        self.assertEqual(client.interest_amount, Decimal("15000.00"))
        self.assertEqual(client.given_amount, Decimal("85000.00"))
        self.assertEqual(client.daily_installment, Decimal("1000.00"))
        self.assertEqual(client.end_date, date(2026, 9, 10))

    def test_mark_today_paid_creates_payment_for_daily_installment(self):
        self.client.login(username="financeuser", password="password")
        loan_date = date.today() - timedelta(days=1)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Kiran",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=loan_date,
            end_date=loan_date + timedelta(days=100),
        )

        response = self.client.post(f"/daily-finance/{finance_client.id}/toggle-today/")

        self.assertEqual(response.status_code, 302)
        payment = DailyFinancePayment.objects.get(client=finance_client)
        self.assertEqual(payment.amount_paid, Decimal("1000.00"))
        self.assertEqual(payment.status, DailyFinancePayment.PaymentStatus.PAID)

    def test_client_detail_page_renders_daily_ledger(self):
        self.client.login(username="financeuser", password="password")
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Lakshmi",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=date(2026, 6, 2),
            end_date=date(2026, 9, 9),
        )

        response = self.client.get(f"/daily-finance/{finance_client.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily Ledger")
        self.assertContains(response, "Update Payment")

    def test_client_detail_extends_ledger_after_planned_duration(self):
        self.client.login(username="financeuser", password="password")
        start_date = date.today() - timedelta(days=120)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Extended Client",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=start_date,
            end_date=start_date + timedelta(days=100),
        )

        response = self.client.get(f"/daily-finance/{finance_client.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "120 Days Shown")
        self.assertContains(response, "D-120")

    def test_new_loan_collection_starts_tomorrow(self):
        self.client.login(username="financeuser", password="password")
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Tomorrow Client",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=100),
        )

        dashboard_response = self.client.get("/daily-finance/")
        self.assertContains(dashboard_response, "Starts Tomorrow")
        self.assertContains(dashboard_response, "Expected: Rs. 0.00")

        toggle_response = self.client.post(f"/daily-finance/{finance_client.id}/toggle-today/")
        self.assertEqual(toggle_response.status_code, 302)
        self.assertFalse(DailyFinancePayment.objects.filter(client=finance_client).exists())

        detail_response = self.client.get(f"/daily-finance/{finance_client.id}/")
        self.assertContains(detail_response, "First Collection Date")
        self.assertContains(detail_response, (date.today() + timedelta(days=1)).strftime("%b %d, %Y"))

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_yesterday_payment_does_not_show_as_paid_today(self):
        self.client.login(username="financeuser", password="password")
        fixed_today = date(2026, 3, 26)
        loan_date = fixed_today - timedelta(days=2)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Night Shift Client",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=loan_date,
            end_date=loan_date + timedelta(days=100),
        )
        DailyFinancePayment.objects.create(
            client=finance_client,
            date=fixed_today - timedelta(days=1),
            amount_paid=Decimal("1000.00"),
            status=DailyFinancePayment.PaymentStatus.PAID,
        )

        with patch("chitfund.views._local_today", return_value=fixed_today):
            response = self.client.get("/daily-finance/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not Paid")
        self.assertEqual(response.context["day_paid_count"], 0)
        self.assertEqual(response.context["total_active_count"], 1)

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_dashboard_can_view_historical_date_status(self):
        self.client.login(username="financeuser", password="password")
        view_date = date(2026, 3, 20)
        loan_date = view_date - timedelta(days=2)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="History Client",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=loan_date,
            end_date=loan_date + timedelta(days=100),
        )
        DailyFinancePayment.objects.create(
            client=finance_client,
            date=view_date,
            amount_paid=Decimal("1000.00"),
            status=DailyFinancePayment.PaymentStatus.PAID,
        )

        response = self.client.get(f"/daily-finance/?date={view_date.isoformat()}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Collection on Mar 20, 2026")
        self.assertEqual(response.context["day_paid_count"], 1)
        self.assertEqual(response.context["total_active_count"], 1)

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_dashboard_partial_payment_counts_in_selected_day_collection(self):
        self.client.login(username="financeuser", password="password")
        fixed_today = date(2026, 3, 26)
        loan_date = fixed_today - timedelta(days=2)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Partial Client",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=loan_date,
            end_date=loan_date + timedelta(days=100),
        )
        DailyFinancePayment.objects.create(
            client=finance_client,
            date=fixed_today,
            amount_paid=Decimal("400.00"),
            status=DailyFinancePayment.PaymentStatus.PARTIAL,
        )

        with patch("chitfund.views._local_today", return_value=fixed_today):
            response = self.client.get("/daily-finance/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["day_collected"], Decimal("400.00"))
        self.assertEqual(response.context["day_paid_count"], 1)
        self.assertEqual(response.context["total_active_count"], 1)
        self.assertContains(response, "Partially Paid")

    @override_settings(TIME_ZONE="Asia/Kolkata")
    def test_dashboard_can_mark_partial_payment(self):
        self.client.login(username="financeuser", password="password")
        fixed_today = date(2026, 3, 26)
        loan_date = fixed_today - timedelta(days=2)
        finance_client = DailyFinanceClient.objects.create(
            user=self.user,
            name="Dashboard Partial",
            asked_amount=Decimal("100000.00"),
            interest_rate_percent=Decimal("5.00"),
            duration_days=100,
            interest_amount=Decimal("15000.00"),
            given_amount=Decimal("85000.00"),
            daily_installment=Decimal("1000.00"),
            start_date=loan_date,
            end_date=loan_date + timedelta(days=100),
        )

        with patch("chitfund.views._local_today", return_value=fixed_today):
            response = self.client.post(
                f"/daily-finance/{finance_client.id}/toggle-today/",
                {
                    "date": fixed_today.isoformat(),
                    "status": DailyFinancePayment.PaymentStatus.PARTIAL,
                    "amount_paid": "450.00",
                },
            )

        self.assertEqual(response.status_code, 302)
        payment = DailyFinancePayment.objects.get(client=finance_client, date=fixed_today)
        self.assertEqual(payment.status, DailyFinancePayment.PaymentStatus.PARTIAL)
        self.assertEqual(payment.amount_paid, Decimal("450.00"))
