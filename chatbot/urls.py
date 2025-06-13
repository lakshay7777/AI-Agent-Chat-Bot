from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('profile/', views.profile_view, name='profile'),
    path('logout/', views.logout_view, name='logout'),
    path('chatbot-api/', views.chatbot_api, name='chatbot_api'),
    path('upload-pdf/', views.upload_pdf, name='upload_pdf'),
    path('add-pdf-url/', views.add_pdf_url, name='add_pdf_url'),
    path('check-pdf-status/', views.check_pdf_status, name='check_pdf_status'),
]