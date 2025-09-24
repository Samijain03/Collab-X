# chatapp/urls.py
from django.urls import path
from . import views

app_name = 'chatapp'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard_view, name='dashboard'), # Add this line
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('search/', views.search_users_view, name='search_users'),
    path('add-contact/<int:user_id>/', views.add_contact_view, name='add_contact'),
]