from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("clients/", views.client_list, name="client-list"),
    path("clients/add/", views.client_create, name="client-create"),
    path("clients/<int:client_id>/edit/", views.client_edit, name="client-edit"),
    path("payments/<int:payment_id>/toggle/", views.toggle_payment_status, name="toggle-payment"),
]
