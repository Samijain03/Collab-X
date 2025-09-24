# Collab-X/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')), # Add this line
    path('', include('chatapp.urls')),
    
]