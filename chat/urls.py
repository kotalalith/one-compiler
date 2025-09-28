from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("chat/", views.chat_endpoint, name="chat_endpoint"),
    path("upload-pdf/", views.upload_pdf, name="upload_pdf"),
    path("clear/", views.clear_chat, name="clear_chat"),
    path("detach-pdf/", views.detach_pdf, name="detach_pdf"),
    path("health/", views.health_check, name="health_check"),
]
