# chatapp/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.template.loader import render_to_string
# --- UPDATED IMPORTS ---
from .forms import (
    SignUpForm, ProfileUpdateForm, CreateGroupForm,
    ChangeGroupNameForm, AddGroupMemberForm, RemoveGroupMemberForm
)
from .models import ContactRequest, Profile, Message, Group, GroupMessage


def _build_workspace_key(chat_type, current_user_id, chat_id):
    if not chat_type or not chat_id:
        return None
    if chat_type == '1on1':
        ordered = sorted([current_user_id, int(chat_id)])
        return f"chat_{ordered[0]}_{ordered[1]}"
    if chat_type == 'group':
        return f"group_{chat_id}"
    return None


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
        'workspace_key': None,
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

    context['workspace_key'] = _build_workspace_key(
        context.get('chat_type'),
        request.user.id,
        context.get('chat_id')
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        chat_html = render_to_string('chatapp/partials/chat_area.html', context, request=request)
        workspace_html = render_to_string('chatapp/partials/workspace_panel.html', context, request=request)
        return JsonResponse({
            'chat_html': chat_html,
            'workspace_html': workspace_html,
            'chat_type': context.get('chat_type'),
            'chat_id': context.get('chat_id'),
            'workspace_key': context.get('workspace_key'),
        })

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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        user_to_request = User.objects.get(id=user_id)
        if request.user.profile.contacts.filter(user=user_to_request).exists():
             msg = f'You are already contacts with {user_to_request.username}.'
             if is_ajax: return JsonResponse({'status': 'info', 'message': msg})
             messages.info(request, msg)
        elif ContactRequest.objects.filter(from_user=request.user, to_user=user_to_request).exists():
            msg = 'You have already sent a request to this user.'
            if is_ajax: return JsonResponse({'status': 'info', 'message': msg})
            messages.info(request, msg)
        else:
            ContactRequest.objects.create(from_user=request.user, to_user=user_to_request)
            msg = f'Contact request sent to {user_to_request.username}!'
            if is_ajax: return JsonResponse({'status': 'success', 'message': msg})
            messages.success(request, msg)
    except User.DoesNotExist:
        msg = 'User not found.'
        if is_ajax: return JsonResponse({'status': 'error', 'message': msg}, status=404)
        messages.error(request, msg)
    
    if is_ajax: return JsonResponse({'status': 'error', 'message': 'Unknown error'})
    return redirect('chatapp:search_users')

@login_required
def accept_contact_request_view(request, request_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        contact_request = ContactRequest.objects.get(id=request_id, to_user=request.user)
        request.user.profile.contacts.add(contact_request.from_user.profile)
        contact_request.from_user.profile.contacts.add(request.user.profile)
        contact_request.delete()
        msg = f'You are now contacts with {contact_request.from_user.username}!'
        
        if is_ajax:
            return JsonResponse({
                'status': 'success', 
                'message': msg,
                'new_contact': {
                    'id': contact_request.from_user.id,
                    'username': contact_request.from_user.username,
                    'display_name': contact_request.from_user.profile.display_name or contact_request.from_user.username,
                    'profile_picture_url': contact_request.from_user.profile.profile_picture.url
                }
            })
        messages.success(request, msg)
    except ContactRequest.DoesNotExist:
        msg = 'Contact request not found or invalid.'
        if is_ajax: return JsonResponse({'status': 'error', 'message': msg}, status=404)
        messages.error(request, msg)
    return redirect('chatapp:dashboard')

@login_required
def decline_contact_request_view(request, request_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        contact_request = ContactRequest.objects.get(id=request_id, to_user=request.user)
        contact_request.delete()
        msg = 'Contact request declined.'
        if is_ajax: return JsonResponse({'status': 'success', 'message': msg})
        messages.info(request, msg)
    except ContactRequest.DoesNotExist:
        msg = 'Contact request not found or invalid.'
        if is_ajax: return JsonResponse({'status': 'error', 'message': msg}, status=404)
        messages.error(request, msg)
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
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
            
            msg = f"Group '{name}' created successfully!"
            
            if is_ajax:
                return JsonResponse({
                    'status': 'success',
                    'message': msg,
                    'group': {
                        'id': new_group.id,
                        'name': new_group.name,
                        'member_count': new_group.members.count()
                    }
                })
            
            messages.success(request, msg)
            # Redirect to the new group's chat page
            return redirect('chatapp:dashboard_group_chat', group_id=new_group.id)
        elif is_ajax:
             return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
             
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


@login_required
@require_POST
def upload_attachment_view(request, chat_type, chat_id):
    if chat_type not in ('1on1', 'group'):
        return HttpResponseBadRequest("Invalid chat type.")

    uploaded_file = request.FILES.get('file')
    caption = request.POST.get('caption', '').strip()

    if not uploaded_file:
        return HttpResponseBadRequest("No file provided.")

    channel_layer = get_channel_layer()
    timestamp = timezone.now().strftime("%I:%M %p")

    if chat_type == '1on1':
        contact_profile = get_object_or_404(Profile, user__id=chat_id)
        user_profile = request.user.profile
        if not user_profile.contacts.filter(user=contact_profile.user).exists():
            return HttpResponseForbidden("Not allowed to upload in this chat.")

        message = Message.objects.create(
            sender=request.user,
            receiver=contact_profile.user,
            content=caption,
            file=uploaded_file,
            file_name=uploaded_file.name
        )
        room_key = _build_workspace_key('1on1', request.user.id, contact_profile.user.id)
        event_payload = {
            'type': 'chat_message',
            'message_id': message.id,
            'message': message.content,
            'sender_username': request.user.username,
            'timestamp': timestamp,
            'attachment_url': message.file.url if message.file else '',
            'attachment_name': message.file_name or uploaded_file.name,
            'sender_display_name': request.user.profile.display_name or request.user.username,
        }
    else:
        group = get_object_or_404(Group, id=chat_id)
        if not group.members.filter(id=request.user.id).exists():
            return HttpResponseForbidden("Not allowed to upload in this group.")

        message = GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=caption,
            file=uploaded_file,
            file_name=uploaded_file.name
        )
        room_key = _build_workspace_key('group', request.user.id, group.id)
        event_payload = {
            'type': 'group_chat_message',
            'message_id': message.id,
            'message': message.content,
            'sender_username': request.user.username,
            'timestamp': timestamp,
            'attachment_url': message.file.url if message.file else '',
            'attachment_name': message.file_name or uploaded_file.name,
            'sender_display_name': request.user.profile.display_name or request.user.username,
        }

    async_to_sync(channel_layer.group_send)(
        room_key,
        event_payload
    )

    return JsonResponse({
        'success': True,
        'message_id': message.id,
        'attachment_name': message.file_name or uploaded_file.name,
        'attachment_url': message.file.url if message.file else '',
        'timestamp': timestamp,
    })