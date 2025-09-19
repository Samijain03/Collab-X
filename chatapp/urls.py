# chatapp/urls.py
from django.urls import path
from . import views

app_name = 'chatapp'

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'), # Add this line
]