# chatapp/views.py

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
# --- UPDATED IMPORTS ---
from .forms import (
    SignUpForm, ProfileUpdateForm, CreateGroupForm,
    ChangeGroupNameForm, AddGroupMemberForm, RemoveGroupMemberForm
)
from .models import ContactRequest, Profile, Message, Group, GroupMessage


# Homepage View
def home(request):
    return render(request, 'chatapp/home.html', {'title': 'Welcome to Collab-X'})

# Signup View
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('chatapp:dashboard')
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('chatapp:dashboard') 
    else:
        form = SignUpForm()
    context = {'form': form, 'title': 'Create an Account'}
    return render(request, 'chatapp/signup.html', context)

# Login View
def login_view(request):
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
                return redirect('chatapp:dashboard') 
    else:
        form = AuthenticationForm()
    context = {'form': form, 'title': 'Log In'}
    return render(request, 'chatapp/login.html', context)

# Logout View
def logout_view(request):
    logout(request)
    return redirect('chatapp:home') 

# --- REPLACED: Dashboard View (Handles 1-to-1 and Group) ---
@login_required
def dashboard_view(request, contact_id=None, group_id=None):
    profile = request.user.profile
    contacts_profiles = profile.contacts.all()
    user_groups = request.user.chat_groups.all()
    incoming_requests = ContactRequest.objects.filter(to_user=request.user)
    
    context = {
        'contacts': contacts_profiles,
        'groups': user_groups,
        'incoming_requests': incoming_requests,
        'selected_contact': None,
        'selected_group': None,
        'messages': [],
        'chat_type': None,
        'chat_id': None,
    }

    if contact_id:
        try:
            selected_contact_profile = Profile.objects.get(user__id=contact_id)
            selected_contact_user = selected_contact_profile.user
            
            if selected_contact_profile in contacts_profiles:
                context['selected_contact'] = selected_contact_profile
                
                messages_query = Message.objects.filter(
                    (Q(sender=request.user) & Q(receiver=selected_contact_user)) |
                    (Q(sender=selected_contact_user) & Q(receiver=request.user))
                ).order_by('timestamp')
                context['messages'] = messages_query
                context['chat_type'] = '1on1'
                context['chat_id'] = selected_contact_profile.user.id
            else:
                messages.error(request, "This user is not in your contact list.")
                return redirect('chatapp:dashboard')
        except Profile.DoesNotExist:
            messages.error(request, "User profile not found.")
            return redirect('chatapp:dashboard')
            
    elif group_id:
        try:
            selected_group = Group.objects.get(id=group_id)
            if selected_group in user_groups:
                context['selected_group'] = selected_group
                context['messages'] = selected_group.messages.all().order_by('timestamp')
                context['chat_type'] = 'group'
                context['chat_id'] = selected_group.id
            else:
                messages.error(request, "You are not a member of this group.")
                return redirect('chatapp:dashboard')
        except Group.DoesNotExist:
            messages.error(request, "Group not found.")
            return redirect('chatapp:dashboard')

    return render(request, 'chatapp/dashboard.html', context)
# --- End of Replaced View ---


@login_required
def search_users_view(request):
    query = request.GET.get('q')
    results = []
    if query:
        results = User.objects.filter(
            Q(username__icontains=query)
        ).exclude(username=request.user.username)
    context = {'results': results}
    return render(request, 'chatapp/search_results.html', context)

@login_required
def send_contact_request_view(request, user_id):
    try:
        user_to_request = User.objects.get(id=user_id)
        if request.user.profile.contacts.filter(user=user_to_request).exists():
             messages.info(request, f'You are already contacts with {user_to_request.username}.')
        elif ContactRequest.objects.filter(from_user=request.user, to_user=user_to_request).exists():
            messages.info(request, 'You have already sent a request to this user.')
        else:
            ContactRequest.objects.create(from_user=request.user, to_user=user_to_request)
            messages.success(request, f'Contact request sent to {user_to_request.username}!')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
    return redirect('chatapp:search_users')

@login_required
def accept_contact_request_view(request, request_id):
    try:
        contact_request = ContactRequest.objects.get(id=request_id, to_user=request.user)
        request.user.profile.contacts.add(contact_request.from_user.profile)
        contact_request.from_user.profile.contacts.add(request.user.profile)
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

@login_required
def settings_view(request):
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('chatapp:settings')
    else:
        form = ProfileUpdateForm(instance=request.user.profile)
    context = {'form': form, 'title': 'Account Settings'}
    return render(request, 'chatapp/settings.html', context)

# --- ADD THIS NEW VIEW AT THE END ---

@login_required
def create_group_view(request):
    if request.method == 'POST':
        # Pass the request.user to the form
        form = CreateGroupForm(request.POST, user=request.user)
        if form.is_valid():
            name = form.cleaned_data['name']
            selected_members = form.cleaned_data['members']
            
            # Create the new group
            new_group = Group.objects.create(name=name, creator=request.user)
            
            # Add the selected members
            new_group.members.set(selected_members)
            # CRITICAL: Add the creator to the group as well!
            new_group.members.add(request.user)
            
            messages.success(request, f"Group '{name}' created successfully!")
            # Redirect to the new group's chat page
            return redirect('chatapp:dashboard_group_chat', group_id=new_group.id)
    else:
        # Pass the request.user to the form
        form = CreateGroupForm(user=request.user)

    return render(request, 'chatapp/create_group.html', {'form': form})

@login_required
def edit_group_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # ADMIN CHECK: Only the creator can edit
    if group.creator != request.user:
        messages.error(request, "You do not have permission to edit this group.")
        return redirect('chatapp:dashboard_group_chat', group_id=group.id)

    if request.method == 'POST':
        form = ChangeGroupNameForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, f"Group name changed to '{group.name}'.")
            return redirect('chatapp:dashboard_group_chat', group_id=group.id)
    else:
        form = ChangeGroupNameForm(instance=group)

    context = {
    'form': form, 
    'group': group, 
    'title': f'Edit {group.name}', 
    'header_icon': 'bi-pencil-square',
    'header_text': '$ chmod +w',
    'button_text': 'Save Changes'
    }
    return render(request, 'chatapp/edit_group.html', context)


@login_required
def add_group_members_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # ADMIN CHECK
    if group.creator != request.user:
        messages.error(request, "You do not have permission to add members.")
        return redirect('chatapp:dashboard_group_chat', group_id=group.id)

    if request.method == 'POST':
        form = AddGroupMemberForm(request.POST, user=request.user, group=group)
        if form.is_valid():
            new_members = form.cleaned_data['members']
            group.members.add(*new_members)
            messages.success(request, f"Added {len(new_members)} new member(s).")
            return redirect('chatapp:dashboard_group_chat', group_id=group.id)
    else:
        form = AddGroupMemberForm(user=request.user, group=group)

    context = {
    'form': form, 
    'group': group, 
    'title': 'Add Members', 
    'header_icon': 'bi-person-plus',
    'header_text': '$ useradd -G',
    'button_text': 'Add Members'
    }
    return render(request, 'chatapp/edit_group.html', context)


@login_required
def remove_group_members_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # ADMIN CHECK
    if group.creator != request.user:
        messages.error(request, "You do not have permission to remove members.")
        return redirect('chatapp:dashboard_group_chat', group_id=group.id)

    if request.method == 'POST':
        form = RemoveGroupMemberForm(request.POST, user=request.user, group=group)
        if form.is_valid():
            members_to_remove = form.cleaned_data['members']
            group.members.remove(*members_to_remove)
            messages.success(request, f"Removed {len(members_to_remove)} member(s).")
            return redirect('chatapp:dashboard_group_chat', group_id=group.id)
    else:
        form = RemoveGroupMemberForm(user=request.user, group=group)

    context = {
    'form': form, 
    'group': group, 
    'title': 'Remove Members', 
    'header_icon': 'bi-person-dash',
    'header_text': '$ gpasswd -d',
    'button_text': 'Remove Members'
    }
    return render(request, 'chatapp/edit_group.html', context)

# chatapp/views.py

@login_required
@require_http_methods(["POST"])
def upload_project_file(request, group_id=None):
    if not group_id:
        return JsonResponse({'error': 'Group ID required'}, status=400)
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({'error': 'No file provided'}, status=400)

    ext = uploaded_file.name.split('.')[-1].lower()
    if ext not in ['py', 'html']:
        return JsonResponse({'error': 'Only .py and .html files allowed'}, status=400)

    file_type = 'py' if ext == 'py' else 'html'
    project_file = ProjectFile.objects.create(
        name=uploaded_file.name,
        file=uploaded_file,
        file_type=file_type,
        group_id=group_id,
        uploaded_by=request.user
    )
    return JsonResponse({
        'id': project_file.id,
        'name': project_file.name,
        'file_type': project_file.file_type,
        'url': project_file.file.url,
        'uploaded_by': project_file.uploaded_by.username,
    })


@login_required
def list_project_files(request, group_id):
    files = ProjectFile.objects.filter(group_id=group_id).values(
        'id', 'name', 'file_type', 'uploaded_by__username'
    )
    return JsonResponse(list(files), safe=False)


@login_required
def get_file_content(request, file_id):
    try:
        pf = ProjectFile.objects.get(id=file_id)
        if request.user not in pf.group.members.all():
            return JsonResponse({'error': 'Not authorized'}, status=403)

        pf.file.open()
        content = pf.file.read().decode('utf-8')
        pf.file.close()
        return JsonResponse({
            'id': pf.id,
            'name': pf.name,
            'content': content,
            'file_type': pf.file_type,
            'url': pf.file.url,
            'uploaded_by': pf.uploaded_by.username,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)