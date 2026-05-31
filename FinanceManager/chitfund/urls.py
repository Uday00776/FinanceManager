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
]
