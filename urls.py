from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    # login
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]
