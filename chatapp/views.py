# chatapp/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from .forms import SignUpForm

def home(request):
    context = {'title': 'Welcome to Collab-X'}
    return render(request, 'chatapp/home.html', context)

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('chatapp:home')
    else:
        form = SignUpForm()
    context = {'form': form, 'title': 'Create an Account'}
    return render(request, 'chatapp/signup.html', context)

# REPLACE the old login_view with this one
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('chatapp:home')
    else:
        form = AuthenticationForm()
    
    context = {'form': form, 'title': 'Log In'}
    return render(request, 'chatapp/login.html', context)

# ADD this new view for logging out
def logout_view(request):
    logout(request)
    return redirect('chatapp:home')