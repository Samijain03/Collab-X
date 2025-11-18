# chatapp/consumers.py

import json
import os
import re
import subprocess
import sys
import tempfile
import time  # <-- ADD THIS
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db.models import Q
from asgiref.sync import sync_to_async

from .models import Message, Profile, Group, GroupMessage, WorkspaceFile
from .gemini_utils import format_chat_history, get_collab_response

def parse_bot_response(response_text):
    """
    Parses the AI response to find a [jump_to: ID] tag.
    Returns the clean content and the jump_id.
    """
    jump_id = None
    content = response_text
    
    match = re.search(r'\[jump_to:\s*(\d+)\s*\]$', response_text)
    
    if match:
        jump_id = int(match.group(1))
        content = re.sub(r'\[jump_to:\s*(\d+)\s*\]$', '', response_text).strip()
        
    return content, jump_id


class ChatConsumer(AsyncWebsocketConsumer):
    
    # ... connect ...
    async def connect(self):
        try:
            self.user = self.scope['user']
            self.contact_id = self.scope['url_route']['kwargs']['contact_id']
            if not self.user.is_authenticated:
                await self.close()
                return
            self.contact_user = await self.get_user(self.contact_id)
            self.contact_profile = await self.get_profile(self.contact_user)
            self.user_profile = await self.get_profile(self.user)
            are_contacts = await self.check_contacts(self.user_profile, self.contact_user)
            if not are_contacts:
                await self.close()
                return
        except User.DoesNotExist:
            await self.close()
            return
        except Profile.DoesNotExist:
            await self.close()
            return
        except Exception as e:
            print(f"[WebSocket] ERROR: {e}")
            await self.close()
            return
        user_ids = sorted([self.user.id, self.contact_user.id])
        self.room_group_name = f'chat_{user_ids[0]}_{user_ids[1]}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    # ... disconnect ...
    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # --- UPDATED `receive` METHOD ---
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'chat_message') 

        if message_type == 'chat_message':
            message_content = data['message']
            if not message_content.strip():
                return 

            # --- UPDATED BOT CHECK ---
            if message_content.startswith('/Collab'):
                is_hidden = message_content.startswith('/Collab hidden')
                await self.handle_collab_command(message_content, is_hidden)
                return
            # --- END BOT CHECK ---

            new_message = await self.save_message(
                sender=self.user,
                receiver=self.contact_user,
                content=message_content
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': new_message.id,
                    'message': new_message.content,
                    'sender_username': self.user.username,
                    'timestamp': new_message.timestamp.strftime("%I:%M %p"),
                    'attachment_url': new_message.file.url if new_message.file else '',
                    'attachment_name': new_message.file_name if new_message.file_name else '',
                    'sender_display_name': self.user_profile.display_name or self.user.username,
                }
            )
        
        elif message_type == 'delete_message':
            message_id = data['message_id']
            deleted_message = await self.delete_message(message_id)
            
            if deleted_message:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'message_deleted', 
                        'message_id': deleted_message.id,
                    }
                )

    # ... chat_message (unchanged) ...
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'content': event['message'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
            'attachment_url': event.get('attachment_url', ''),
            'attachment_name': event.get('attachment_name', ''),
            'sender_display_name': event.get('sender_display_name', ''),
        }))

    # ... message_deleted (unchanged) ...
    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

    # --- NEW `handle_collab_command` ---
    async def handle_collab_command(self, command_text, is_hidden):
        # Generate a unique ID for this request
        request_id = f"bot-{self.user.id}-{int(time.time())}"
        
        # 1. Send "Thinking..." message
        thinking_payload_js = {
            'type': 'bot_message',
            'status': 'thinking',
            'content': "Thinking...",
            'sender_username': 'Collab-X',
            'jump_id': None,
            'request_id': request_id
        }
        
        if is_hidden:
            # Send "Thinking..." only to the user
            await self.send(text_data=json.dumps(thinking_payload_js))
        else:
            # Broadcast "Thinking..." to the group
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'bot_message', # This is the handler name
                'status': 'thinking',
                'message': "Thinking...",
                'sender_username': 'Collab-X',
                'jump_id': None,
                'request_id': request_id
            })
        
        # 2. Extract user's actual query
        if is_hidden:
            user_query = command_text.replace('/Collab hidden', '').strip()
        else:
            user_query = command_text.replace('/Collab', '').strip()
        if not user_query:
            user_query = "Summarize our chat so far."
            
        # 3. Get chat history
        chat_history_string = await self.get_chat_history()
        
        # 4. Call Gemini (wrapped)
        bot_response_text = await database_sync_to_async(get_collab_response)(
            chat_history_string, 
            user_query
        )
        clean_content, jump_id = parse_bot_response(bot_response_text)
        
        # 5. Send the final response
        final_payload_js = {
            'type': 'bot_message',
            'status': 'complete',
            'content': clean_content,
            'sender_username': 'Collab-X',
            'jump_id': jump_id,
            'request_id': request_id # Use same ID
        }

        if is_hidden:
            # Send final response only to the user
            await self.send(text_data=json.dumps(final_payload_js))
        else:
            # Broadcast final response to the group
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'bot_message', # Handler name
                'status': 'complete',
                'message': clean_content,
                'sender_username': 'Collab-X',
                'jump_id': jump_id,
                'request_id': request_id
            })

    # --- UPDATED `bot_message` HANDLER ---
    async def bot_message(self, event):
        """ Handles broadcasting 'bot_message' types from the group. """
        await self.send(text_data=json.dumps({
            'type': 'bot_message', # Type for JS client
            'status': event.get('status', 'complete'),
            'content': event['message'], # Content is in 'message'
            'sender_username': event['sender_username'],
            'jump_id': event.get('jump_id', None),
            'request_id': event.get('request_id')
        }))
        
    # ... get_chat_history (unchanged) ...
    @database_sync_to_async
    def get_chat_history(self):
        messages_queryset = Message.objects.filter(
            (Q(sender=self.user) & Q(receiver=self.contact_user)) |
            (Q(sender=self.contact_user) & Q(receiver=self.user)),
            is_deleted=False
        ).order_by('timestamp')
        return format_chat_history(messages_queryset)

    # ... Other DB helpers (get_user, get_profile, etc. are unchanged) ...
    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)
    @database_sync_to_async
    def get_profile(self, user):
        return Profile.objects.get(user=user)
    @database_sync_to_async
    def check_contacts(self, user_profile, contact_user):
        return user_profile.contacts.filter(user=contact_user).exists()
    @database_sync_to_async
    def save_message(self, sender, receiver, content):
        return Message.objects.create(sender=sender, receiver=receiver, content=content)
    @database_sync_to_async
    def delete_message(self, message_id):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user)
            if not msg.is_deleted:
                msg.is_deleted = True
                msg.content = "This message was deleted."
                msg.save()
                return msg
        except Message.DoesNotExist:
            return None
        return None


# --- UPDATES FOR GroupChatConsumer ---

class GroupChatConsumer(AsyncWebsocketConsumer):
    
    # ... connect (unchanged) ...
    async def connect(self):
        try:
            self.user = self.scope['user']
            self.group_id = self.scope['url_route']['kwargs']['group_id']
            if not self.user.is_authenticated:
                await self.close()
                return
            self.group = await self.get_group(self.group_id)
            is_member = await self.check_membership(self.group, self.user)
            if not is_member:
                await self.close()
                return
            self.user_profile = await self.get_profile(self.user)
        except Group.DoesNotExist:
            await self.close()
            return
        except Exception as e:
            print(f"[WebSocket] ERROR: {e}")
            await self.close()
            return
        self.room_group_name = f'group_{self.group_id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    # ... disconnect (unchanged) ...
    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # --- UPDATED `receive` METHOD ---
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'chat_message')

        if message_type == 'chat_message':
            message_content = data['message']
            if not message_content.strip():
                return
            
            # --- UPDATED BOT CHECK ---
            if message_content.startswith('/Collab'):
                is_hidden = message_content.startswith('/Collab hidden')
                await self.handle_collab_command(message_content, is_hidden)
                return
            # --- END BOT CHECK ---

            new_message = await self.save_group_message(
                group=self.group,
                sender=self.user,
                content=message_content
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_chat_message',
                    'message_id': new_message.id,
                    'message': new_message.content,
                    'sender_username': self.user.username,
                    'timestamp': new_message.timestamp.strftime("%I:%M %p"),
                    'attachment_url': new_message.file.url if new_message.file else '',
                    'attachment_name': new_message.file_name if new_message.file_name else '',
                    'sender_display_name': self.user.profile.display_name or self.user.username,
                }
            )
            
        elif message_type == 'delete_message':
            message_id = data['message_id']
            deleted_message = await self.delete_group_message(message_id)
            
            if deleted_message:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'message_deleted',
                        'message_id': deleted_message.id,
                    }
                )

    # ... group_chat_message (unchanged) ...
    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'content': event['message'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
            'attachment_url': event.get('attachment_url', ''),
            'attachment_name': event.get('attachment_name', ''),
            'sender_display_name': event.get('sender_display_name', ''),
        }))
        
    # ... message_deleted (unchanged) ...
    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

    # --- NEW `handle_collab_command` ---
    async def handle_collab_command(self, command_text, is_hidden):
        request_id = f"bot-{self.user.id}-{int(time.time())}"
        
        thinking_payload_js = {
            'type': 'bot_message',
            'status': 'thinking',
            'content': "Thinking...",
            'sender_username': 'Collab-X',
            'jump_id': None,
            'request_id': request_id
        }
        
        if is_hidden:
            await self.send(text_data=json.dumps(thinking_payload_js))
        else:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'bot_message',
                'status': 'thinking',
                'message': "Thinking...",
                'sender_username': 'Collab-X',
                'jump_id': None,
                'request_id': request_id
            })
        
        if is_hidden:
            user_query = command_text.replace('/Collab hidden', '').strip()
        else:
            user_query = command_text.replace('/Collab', '').strip()
        if not user_query:
            user_query = "Summarize this group chat so far."
            
        chat_history_string = await self.get_chat_history()
        
        bot_response_text = await database_sync_to_async(get_collab_response)(
            chat_history_string, 
            user_query
        )
        clean_content, jump_id = parse_bot_response(bot_response_text)
        
        final_payload_js = {
            'type': 'bot_message',
            'status': 'complete',
            'content': clean_content,
            'sender_username': 'Collab-X',
            'jump_id': jump_id,
            'request_id': request_id
        }

        if is_hidden:
            await self.send(text_data=json.dumps(final_payload_js))
        else:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'bot_message',
                'status': 'complete',
                'message': clean_content,
                'sender_username': 'Collab-X',
                'jump_id': jump_id,
                'request_id': request_id
            })

    # --- UPDATED `bot_message` HANDLER ---
    async def bot_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bot_message',
            'status': event.get('status', 'complete'),
            'content': event['message'],
            'sender_username': event['sender_username'],
            'jump_id': event.get('jump_id', None),
            'request_id': event.get('request_id')
        }))
        
    # ... get_chat_history (unchanged) ...
    @database_sync_to_async
    def get_chat_history(self):
        messages_queryset = self.group.messages.filter(is_deleted=False).order_by('timestamp')
        return format_chat_history(messages_queryset)

    # ... Other DB helpers (get_group, etc. are unchanged) ...
    @database_sync_to_async
    def get_group(self, group_id):
        return Group.objects.get(id=group_id)
    @database_sync_to_async
    def check_membership(self, group, user):
        return group.members.filter(id=user.id).exists()
    @database_sync_to_async
    def save_group_message(self, group, sender, content):
        return GroupMessage.objects.create(group=group, sender=sender, content=content)
    @database_sync_to_async
    def delete_group_message(self, message_id):
        try:
            msg = GroupMessage.objects.get(id=message_id, sender=self.user)
            if not msg.is_deleted:
                msg.is_deleted = True
                msg.content = "This message was deleted."
                msg.save()
                return msg
        except GroupMessage.DoesNotExist:
            return None
        return None

    @database_sync_to_async
    def get_profile(self, user):
        return Profile.objects.get(user=user)


class WorkspaceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.workspace_key = self.scope['url_route']['kwargs']['workspace_key']

        if not self.user.is_authenticated:
            await self.close()
            return

        has_access = await self.check_workspace_access()
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.workspace_key, self.channel_name)
        await self.accept()

        files = await self.get_workspace_files()
        await self.send(text_data=json.dumps({
            'type': 'workspace_bootstrap',
            'files': files
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'workspace_key'):
            await self.channel_layer.group_discard(self.workspace_key, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'create_file':
            await self.handle_create_file(data)
        elif action == 'delete_file':
            await self.handle_delete_file(data)
        elif action == 'rename_file':
            await self.handle_rename_file(data)
        elif action == 'update_content':
            await self.handle_update_content(data)
        elif action == 'run_file':
            await self.handle_run_file(data)

    async def handle_create_file(self, data):
        name = (data.get('name') or '').strip()
        language = data.get('language')

        if not name or language not in dict(WorkspaceFile.LANGUAGE_CHOICES):
            return

        file_obj = await self.create_workspace_file(name, language)
        if file_obj:
            payload = {
                'type': 'workspace_event',
                'event': 'file_created',
                'file': file_obj
            }
            await self.channel_layer.group_send(self.workspace_key, payload)

    async def handle_delete_file(self, data):
        file_id = data.get('file_id')
        deleted_id = await self.delete_workspace_file(file_id)
        if deleted_id:
            payload = {
                'type': 'workspace_event',
                'event': 'file_deleted',
                'file_id': deleted_id
            }
            await self.channel_layer.group_send(self.workspace_key, payload)

    async def handle_rename_file(self, data):
        file_id = data.get('file_id')
        new_name = (data.get('name') or '').strip()
        renamed = await self.rename_workspace_file(file_id, new_name)
        if renamed:
            payload = {
                'type': 'workspace_event',
                'event': 'file_renamed',
                'file': renamed
            }
            await self.channel_layer.group_send(self.workspace_key, payload)

    async def handle_update_content(self, data):
        file_id = data.get('file_id')
        content = data.get('content', '')
        updated = await self.update_workspace_file(file_id, content)
        if updated:
            payload = {
                'type': 'workspace_event',
                'event': 'file_updated',
                'file': updated,
                'updated_by': self.user.username
            }
            await self.channel_layer.group_send(self.workspace_key, payload)

    async def handle_run_file(self, data):
        file_id = data.get('file_id')
        file_data = await self.get_workspace_file(file_id)
        if not file_data:
            return

        if file_data['language'] == 'python':
            result = await sync_to_async(self._run_python)(file_data['content'])
        else:
            result = {
                'stdout': '',
                'stderr': '',
                'html': file_data['content']
            }

        response = {
            'type': 'workspace_event',
            'event': 'run_result',
            'file_id': file_id,
            'language': file_data['language'],
            'requested_by': self.user.username,
            'result': result
        }

        await self.channel_layer.group_send(self.workspace_key, response)

    async def workspace_event(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def check_workspace_access(self):
        if self.workspace_key.startswith('chat_'):
            try:
                _, user_a, user_b = self.workspace_key.split('_')
                user_ids = {int(user_a), int(user_b)}
                if self.user.id not in user_ids:
                    return False
                other_id = (user_ids - {self.user.id}).pop()
                profile = Profile.objects.get(user=self.user)
                return profile.contacts.filter(user__id=other_id).exists()
            except (ValueError, Profile.DoesNotExist):
                return False
        elif self.workspace_key.startswith('group_'):
            try:
                _, group_id = self.workspace_key.split('_')
                return Group.objects.filter(id=int(group_id), members=self.user).exists()
            except ValueError:
                return False
        return False

    @database_sync_to_async
    def get_workspace_files(self):
        return [
            {
                'id': file.id,
                'name': file.name,
                'language': file.language,
                'content': file.content,
                'updated_at': file.updated_at.isoformat(),
            }
            for file in WorkspaceFile.objects.filter(workspace_key=self.workspace_key)
        ]

    @database_sync_to_async
    def create_workspace_file(self, name, language):
        default_content = self._default_content(language, name)
        file_obj, created = WorkspaceFile.objects.get_or_create(
            workspace_key=self.workspace_key,
            name=name,
            defaults={
                'language': language,
                'content': default_content,
                'created_by': self.user,
            }
        )
        if not created:
            return None
        return {
            'id': file_obj.id,
            'name': file_obj.name,
            'language': file_obj.language,
            'content': file_obj.content,
            'updated_at': file_obj.updated_at.isoformat(),
        }

    @database_sync_to_async
    def delete_workspace_file(self, file_id):
        try:
            file_obj = WorkspaceFile.objects.get(id=file_id, workspace_key=self.workspace_key)
            file_obj.delete()
            return file_id
        except WorkspaceFile.DoesNotExist:
            return None

    @database_sync_to_async
    def rename_workspace_file(self, file_id, new_name):
        if not new_name:
            return None
        try:
            file_obj = WorkspaceFile.objects.get(id=file_id, workspace_key=self.workspace_key)
            file_obj.name = new_name
            file_obj.save(update_fields=['name', 'updated_at'])
            return {
                'id': file_obj.id,
                'name': file_obj.name,
                'language': file_obj.language,
                'content': file_obj.content,
                'updated_at': file_obj.updated_at.isoformat(),
            }
        except WorkspaceFile.DoesNotExist:
            return None

    @database_sync_to_async
    def update_workspace_file(self, file_id, content):
        try:
            file_obj = WorkspaceFile.objects.get(id=file_id, workspace_key=self.workspace_key)
            file_obj.content = content
            file_obj.save(update_fields=['content', 'updated_at'])
            return {
                'id': file_obj.id,
                'name': file_obj.name,
                'language': file_obj.language,
                'content': file_obj.content,
                'updated_at': file_obj.updated_at.isoformat(),
            }
        except WorkspaceFile.DoesNotExist:
            return None

    @database_sync_to_async
    def get_workspace_file(self, file_id):
        try:
            file_obj = WorkspaceFile.objects.get(id=file_id, workspace_key=self.workspace_key)
            return {
                'id': file_obj.id,
                'name': file_obj.name,
                'language': file_obj.language,
                'content': file_obj.content,
            }
        except WorkspaceFile.DoesNotExist:
            return None

    def _default_content(self, language, name):
        if language == 'python':
            return f"""def main():
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
"""
        return "<!-- Collaborative HTML file -->\n<!DOCTYPE html>\n<html>\n  <head>\n    <title>Collab-X</title>\n  </head>\n  <body>\n    <h1>Hello from {name}</h1>\n  </body>\n</html>\n"

    def _run_python(self, content):
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            completed = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=5
            )
            return {
                'stdout': completed.stdout,
                'stderr': completed.stderr,
                'returncode': completed.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                'stdout': '',
                'stderr': 'Execution timed out after 5 seconds.',
                'returncode': -1,
            }
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)