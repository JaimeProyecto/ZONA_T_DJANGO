from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path("", views.login_view, name="login"),
    path("redirect/", views.redirect_dashboard, name="redirect_dashboard"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
