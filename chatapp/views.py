from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages

# Homepage View
def home(request):
    return render(request, 'chatapp/home.html', {'title': 'Welcome to Collab-X'})

# Dashboard View
@login_required
def dashboard_view(request):
    return render(request, 'chatapp/dashboard.html')

# Signup View
def signup_view(request):
    # If user is already logged in, redirect them to the dashboard
    if request.user.is_authenticated:
        return redirect('chatapp:dashboard')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('chatapp:dashboard') # Redirect to dashboard
    else:
        form = SignUpForm()
    
    context = {'form': form, 'title': 'Create an Account'}
    return render(request, 'chatapp/signup.html', context)

# Login View
def login_view(request):
    # If user is already logged in, redirect them to the dashboard
    if request.user.is_authenticated:
        return redirect('chatapp:dashboard')
        
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # Django will now automatically redirect to LOGIN_REDIRECT_URL ('/dashboard/')
                return redirect('chatapp:dashboard') 
    else:
        form = AuthenticationForm()
    
    context = {'form': form, 'title': 'Log In'}
    return render(request, 'chatapp/login.html', context)

# Logout View
def logout_view(request):
    logout(request)
    return redirect('chatapp:home') # Redirect to homepage after logout

@login_required
def dashboard_view(request):
    # Get the profile of the current user to access their contacts
    profile = request.user.profile
    contacts = profile.contacts.all()
    
    context = {
        'contacts': contacts,
    }
    return render(request, 'chatapp/dashboard.html', context)

@login_required
def search_users_view(request):
    query = request.GET.get('q')
    results = []
    if query:
        # Search for users by username, excluding the current user
        results = User.objects.filter(
            Q(username__icontains=query)
        ).exclude(username=request.user.username)
    
    context = {
        'results': results,
    }
    return render(request, 'chatapp/search_results.html', context)

@login_required
def add_contact_view(request, user_id):
    try:
        contact_to_add = User.objects.get(id=user_id)
        request.user.profile.contacts.add(contact_to_add.profile)
        messages.success(request, f'{contact_to_add.username} has been added to your contacts!')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
    
    return redirect('chatapp:dashboard')