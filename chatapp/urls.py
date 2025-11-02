# chatapp/urls.py
from django.urls import path
from . import views

app_name = 'chatapp'

urlpatterns = [
    # General Auth/Navigation
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('settings/', views.settings_view, name='settings'), # User settings page

    # Dashboard and Chat Display
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/<int:contact_id>/', views.dashboard_view, name='dashboard_chat'),
    
    # Contact Management
    path('search/', views.search_users_view, name='search_users'),
    path('send-request/<int:user_id>/', views.send_contact_request_view, name='send_contact_request'),
    path('accept-request/<int:request_id>/', views.accept_contact_request_view, name='accept_contact_request'),
    path('decline-request/<int:request_id>/', views.decline_contact_request_view, name='decline_contact_request'),

]