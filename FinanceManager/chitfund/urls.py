from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("chitfund/", views.dashboard, name="dashboard"),
    path("clients/", views.client_list, name="client-list"),
    path("clients/add/", views.client_create, name="client-create"),
    path("clients/<int:client_id>/edit/", views.client_edit, name="client-edit"),
    path("payments/<int:payment_id>/toggle/", views.toggle_payment_status, name="toggle-payment"),
    path("expenses/", views.daily_expense_list, name="daily-expense-list"),
    path("expenses/add/", views.daily_expense_create, name="daily-expense-create"),
]
