from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
from .forms import SignUpForm, ProfileUpdateForm # Add ProfileUpdateForm to imports by kk
from .models import ContactRequest # 👈 ADD THIS IMPORT

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
    profile = request.user.profile
    contacts = profile.contacts.all()
    # Get incoming contact requests for the logged-in user
    incoming_requests = ContactRequest.objects.filter(to_user=request.user)
    
    context = {
        'contacts': contacts,
        'incoming_requests': incoming_requests, # 👈 Add requests to context
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
def send_contact_request_view(request, user_id):
    try:
        user_to_request = User.objects.get(id=user_id)
        # Check if a request already exists or if they are already contacts
        if request.user.profile.contacts.filter(user=user_to_request).exists():
             messages.info(request, f'You are already contacts with {user_to_request.username}.')
        elif ContactRequest.objects.filter(from_user=request.user, to_user=user_to_request).exists():
            messages.info(request, 'You have already sent a request to this user.')
        else:
            ContactRequest.objects.create(from_user=request.user, to_user=user_to_request)
            messages.success(request, f'Contact request sent to {user_to_request.username}!')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
    
    return redirect('chatapp:search_users') # Redirect back to search results

@login_required
def accept_contact_request_view(request, request_id):
    try:
        contact_request = ContactRequest.objects.get(id=request_id, to_user=request.user)
        
        # Add both users to each other's contact lists
        request.user.profile.contacts.add(contact_request.from_user.profile)
        contact_request.from_user.profile.contacts.add(request.user.profile)
        
        # Delete the request object after accepting
        contact_request.delete()
        messages.success(request, f'You are now contacts with {contact_request.from_user.username}!')
    except ContactRequest.DoesNotExist:
        messages.error(request, 'Contact request not found or invalid.')
        
    return redirect('chatapp:dashboard')

@login_required
def decline_contact_request_view(request, request_id):
    try:
        contact_request = ContactRequest.objects.get(id=request_id, to_user=request.user)
        contact_request.delete()
        messages.info(request, 'Contact request declined.')
    except ContactRequest.DoesNotExist:
        messages.error(request, 'Contact request not found or invalid.')
        
    return redirect('chatapp:dashboard')

# --- Add this new view at the end of the file by kk ---
@login_required
def settings_view(request):
    if request.method == 'POST':
        # Pass request.POST for form data and request.FILES for uploaded files
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('chatapp:settings') # Redirect back to the settings page
    else:
        # For a GET request, create a form instance with the user's current profile data
        form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'form': form,
        'title': 'Account Settings'
    }
    return render(request, 'chatapp/settings.html', context)
