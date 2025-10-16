from django.urls import path
from . import views

app_name = "notificaciones"
urlpatterns = [
    path("subscribe/", views.subscribe, name="subscribe"),
    path("debug/", views.debug, name="debug"),
    path("test-me/", views.test_push_me, name="test_me"),
    path("status/", views.status, name="status"),

]
