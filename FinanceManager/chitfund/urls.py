from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("chitfund/", views.chitfund_management, name="chitfund-management"),
    path("chitfund/<slug:fund_slug>/", views.dashboard, name="dashboard"),
    path("chitfund/<slug:fund_slug>/clients/", views.client_list, name="client-list"),
    path("chitfund/<slug:fund_slug>/clients/add/", views.client_create, name="client-create"),
    path(
        "chitfund/<slug:fund_slug>/clients/<int:client_id>/edit/",
        views.client_edit,
        name="client-edit",
    ),
    path("clients/", views.legacy_client_list_redirect, name="legacy-client-list"),
    path("clients/add/", views.legacy_client_create_redirect, name="legacy-client-create"),
    path("payments/<int:payment_id>/toggle/", views.toggle_payment_status, name="toggle-payment"),
    path("expenses/", views.daily_expense_list, name="daily-expense-list"),
    path("expenses/add/", views.daily_expense_create, name="daily-expense-create"),
    # Credit Tracker URLs
    path("credits/", views.credits_dashboard, name="credits-dashboard"),
    path("credits/<int:friend_id>/", views.credits_dashboard, name="credits-detail"),
    path("credits/add-friend/", views.add_friend, name="add-friend"),
    path("credits/<int:friend_id>/add-transaction/", views.add_transaction, name="add-transaction"),
    path("credits/friend/<int:friend_id>/delete/", views.delete_friend, name="delete-friend"),
    path("credits/transaction/<int:transaction_id>/delete/", views.delete_transaction, name="delete-transaction"),
    # Daily Finance Tracker URLs
    path("daily-finance/", views.daily_finance_dashboard, name="daily-finance-dashboard"),
    path("daily-finance/add/", views.daily_finance_client_create, name="daily-finance-client-create"),
    path("daily-finance/<int:client_id>/", views.daily_finance_client_detail, name="daily-finance-client-detail"),
    path("daily-finance/<int:client_id>/edit/", views.daily_finance_client_edit, name="daily-finance-client-edit"),
    path("daily-finance/<int:client_id>/delete/", views.daily_finance_client_delete, name="daily-finance-client-delete"),
    path("daily-finance/<int:client_id>/toggle-today/", views.daily_finance_toggle_today_payment, name="daily-finance-toggle-today"),
    path("daily-finance/<int:client_id>/update-day/", views.daily_finance_update_day_payment, name="daily-finance-update-day"),
]

