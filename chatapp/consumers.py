# chatapp/consumers.py

import json
import re
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Message, Profile, Group, GroupMessage
from .gemini_utils import format_chat_history, get_collab_response
from .code_executor import execute_python_code

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


async def handle_collab_command_shared(consumer, command_text, is_hidden, default_query):
    """
    Shared handler for /Collab command in both ChatConsumer and GroupChatConsumer.
    Reduces code duplication.
    """
    request_id = f"bot-{consumer.user.id}-{int(time.time())}"
    
    thinking_payload_js = {
        'type': 'bot_message',
        'status': 'thinking',
        'content': "Thinking...",
        'sender_username': 'Collab-X',
        'jump_id': None,
        'request_id': request_id
    }
    
    if is_hidden:
        await consumer.send(text_data=json.dumps(thinking_payload_js))
    else:
        await consumer.channel_layer.group_send(consumer.room_group_name, {
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
        user_query = default_query
        
    chat_history_string = await consumer.get_chat_history()
    
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
        await consumer.send(text_data=json.dumps(final_payload_js))
    else:
        await consumer.channel_layer.group_send(consumer.room_group_name, {
            'type': 'bot_message',
            'status': 'complete',
            'message': clean_content,
            'sender_username': 'Collab-X',
            'jump_id': jump_id,
            'request_id': request_id
        })


class ChatConsumer(AsyncWebsocketConsumer):
    
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

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'chat_message') 

        if message_type == 'chat_message':
            message_content = data['message']
            if not message_content.strip():
                return 

            if message_content.startswith('/Collab'):
                is_hidden = message_content.startswith('/Collab hidden')
                await handle_collab_command_shared(self, message_content, is_hidden, "Summarize our chat so far.")
                return

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
                    'timestamp': new_message.timestamp.strftime("%I:%M %p") 
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

        elif message_type == 'execute_code':
            code = data.get('code', '')
            if code:
                result = await database_sync_to_async(execute_python_code)(code)
                await self.send(text_data=json.dumps({
                    'type': 'execution_result',
                    'output': result
                }))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message', 
            'message_id': event['message_id'], 
            'content': event['message'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))


    async def bot_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bot_message',
            'status': event.get('status', 'complete'),
            'content': event['message'],
            'sender_username': event['sender_username'],
            'jump_id': event.get('jump_id', None),
            'request_id': event.get('request_id')
        }))
        
    @database_sync_to_async
    def get_chat_history(self):
        # Optimize: Use select_related and limit to last 50 messages for AI context
        messages_queryset = Message.objects.filter(
            (Q(sender=self.user) & Q(receiver=self.contact_user)) |
            (Q(sender=self.contact_user) & Q(receiver=self.user)),
            is_deleted=False
        ).select_related('sender', 'sender__profile').order_by('-timestamp')[:50]
        # Reverse to get chronological order
        return format_chat_history(reversed(messages_queryset))

    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.select_related('profile').get(id=user_id)
    @database_sync_to_async
    def get_profile(self, user):
        return Profile.objects.select_related('user').get(user=user)
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


class GroupChatConsumer(AsyncWebsocketConsumer):
    
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

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type', 'chat_message')

        if message_type == 'chat_message':
            message_content = data['message']
            if not message_content.strip():
                return
            
            if message_content.startswith('/Collab'):
                is_hidden = message_content.startswith('/Collab hidden')
                await handle_collab_command_shared(self, message_content, is_hidden, "Summarize this group chat so far.")
                return

            new_message = await self.save_group_message(
                group=self.group,
                sender=self.user,
                content=message_content
            )
            # Get sender display name for group messages
            sender_display_name = await self.get_sender_display_name(self.user)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'group_chat_message',
                    'message_id': new_message.id, 
                    'message': new_message.content,
                    'sender_username': self.user.username,
                    'sender_display_name': sender_display_name,
                    'timestamp': new_message.timestamp.strftime("%I:%M %p")
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

        elif message_type == 'execute_code':
            code = data.get('code', '')
            if code:
                result = await database_sync_to_async(execute_python_code)(code)
                await self.send(text_data=json.dumps({
                    'type': 'execution_result',
                    'output': result
                }))

    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message', 
            'message_id': event['message_id'], 
            'content': event['message'],
            'sender_username': event['sender_username'],
            'sender_display_name': event.get('sender_display_name'),
            'timestamp': event['timestamp'],
        }))
        
    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))


    async def bot_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'bot_message',
            'status': event.get('status', 'complete'),
            'content': event['message'],
            'sender_username': event['sender_username'],
            'jump_id': event.get('jump_id', None),
            'request_id': event.get('request_id')
        }))
        
    @database_sync_to_async
    def get_chat_history(self):
        # Optimize: Use select_related and limit to last 50 messages for AI context
        messages_queryset = self.group.messages.filter(
            is_deleted=False
        ).select_related('sender', 'sender__profile').order_by('-timestamp')[:50]
        # Reverse to get chronological order
        return format_chat_history(reversed(messages_queryset))

    @database_sync_to_async
    def get_group(self, group_id):
        return Group.objects.prefetch_related('members').get(id=group_id)
    @database_sync_to_async
    def check_membership(self, group, user):
        return group.members.filter(id=user.id).exists()
    @database_sync_to_async
    def save_group_message(self, group, sender, content):
        return GroupMessage.objects.create(group=group, sender=sender, content=content)
    @database_sync_to_async
    def get_sender_display_name(self, user):
        # Use select_related to avoid extra query if profile not already loaded
        user_with_profile = User.objects.select_related('profile').get(id=user.id)
        return user_with_profile.profile.display_name or user_with_profile.username
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

class WorkspaceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.workspace_key = self.scope['url_route']['kwargs']['workspace_key']
        self.room_group_name = f'workspace_{self.workspace_key}'
        self.user = self.scope['user']
        self.active_file_id = None
        self.cursor_position = 0
        self.user_color = await self.get_user_color()

        if not self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        
        # Notify others that this user joined
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'user_id': self.user.id,
                'username': self.user.username,
                'display_name': await self.get_display_name(),
                'user_color': self.user_color,
                'channel_name': self.channel_name
            }
        )

    async def disconnect(self, close_code):
        # Notify others that this user left
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_left',
                'user_id': self.user.id,
                'channel_name': self.channel_name
            }
        )
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'list_files':
            files = await self.get_files()
            await self.send(text_data=json.dumps({
                'type': 'file_list',
                'files': files
            }))

        elif message_type == 'create_node':
            name = data.get('name')
            node_type = data.get('node_type')
            parent_id = data.get('parent_id')
            
            if name and node_type:
                new_node = await self.create_node(name, node_type, parent_id)
                if new_node:
                    await self.broadcast_file_list()

        elif message_type == 'read_file':
            node_id = data.get('node_id')
            if node_id:
                content, language = await self.read_file_content(node_id)
                await self.send(text_data=json.dumps({
                    'type': 'file_content',
                    'node_id': node_id,
                    'content': content,
                    'language': language
                }))

        elif message_type == 'write_file':
            # Support both full content (legacy) and incremental updates (new)
            node_id = data.get('node_id')
            content = data.get('content')
            delta = data.get('delta')  # Incremental update: {type: 'insert'|'delete', position: int, text: str, length: int}
            cursor_pos = data.get('cursor_position', 0)
            
            if node_id is not None:
                if delta:
                    # Incremental update - apply delta to file
                    await self.apply_delta(node_id, delta)
                elif content is not None:
                    # Full content update (legacy/fallback)
                    await self.update_file_content(node_id, content)
                
                # Update user's active file and cursor position
                self.active_file_id = node_id
                self.cursor_position = cursor_pos
                
                # Broadcast update to others
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'file_updated',
                        'node_id': node_id,
                        'content': content,  # For legacy support
                        'delta': delta,  # Incremental update
                        'cursor_position': cursor_pos,
                        'sender_channel_name': self.channel_name,
                        'user_id': self.user.id,
                        'username': self.user.username,
                        'display_name': await self.get_display_name(),
                        'user_color': self.user_color
                    }
                )
        
        elif message_type == 'cursor_update':
            # Update cursor position without changing content
            node_id = data.get('node_id')
            cursor_pos = data.get('cursor_position', 0)
            selection_start = data.get('selection_start')
            selection_end = data.get('selection_end')
            
            if node_id:
                self.active_file_id = node_id
                self.cursor_position = cursor_pos
                
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'cursor_updated',
                        'node_id': node_id,
                        'cursor_position': cursor_pos,
                        'selection_start': selection_start,
                        'selection_end': selection_end,
                        'sender_channel_name': self.channel_name,
                        'user_id': self.user.id,
                        'username': self.user.username,
                        'display_name': await self.get_display_name(),
                        'user_color': self.user_color
                    }
                )
        
        elif message_type == 'file_focus':
            # User opened/focused a file
            node_id = data.get('node_id')
            if node_id:
                self.active_file_id = node_id
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'file_focused',
                        'node_id': node_id,
                        'sender_channel_name': self.channel_name,
                        'user_id': self.user.id,
                        'username': self.user.username,
                        'display_name': await self.get_display_name(),
                        'user_color': self.user_color
                    }
                )

        elif message_type == 'delete_node':
            node_id = data.get('node_id')
            if node_id:
                await self.delete_node(node_id)
                await self.broadcast_file_list()

    async def file_updated(self, event):
        # Don't echo back to the sender to avoid cursor jumps/conflicts
        if self.channel_name != event.get('sender_channel_name'):
            payload = {
                'type': 'file_update',
                'node_id': event['node_id'],
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'display_name': event.get('display_name'),
                'user_color': event.get('user_color')
            }
            # Include delta if present (incremental update)
            if event.get('delta'):
                payload['delta'] = event['delta']
                payload['cursor_position'] = event.get('cursor_position')
            # Include full content for legacy support or fallback
            elif event.get('content') is not None:
                payload['content'] = event['content']
            
            await self.send(text_data=json.dumps(payload))
    
    async def cursor_updated(self, event):
        # Don't echo back to the sender
        if self.channel_name != event.get('sender_channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'cursor_update',
                'node_id': event['node_id'],
                'cursor_position': event.get('cursor_position'),
                'selection_start': event.get('selection_start'),
                'selection_end': event.get('selection_end'),
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'display_name': event.get('display_name'),
                'user_color': event.get('user_color')
            }))
    
    async def file_focused(self, event):
        # Don't echo back to the sender
        if self.channel_name != event.get('sender_channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'file_focus',
                'node_id': event['node_id'],
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'display_name': event.get('display_name'),
                'user_color': event.get('user_color')
            }))
    
    async def user_joined(self, event):
        # Don't echo back to the sender
        if self.channel_name != event.get('channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'user_joined',
                'user_id': event.get('user_id'),
                'username': event.get('username'),
                'display_name': event.get('display_name'),
                'user_color': event.get('user_color')
            }))
    
    async def user_left(self, event):
        # Don't echo back to the sender
        if self.channel_name != event.get('channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'user_left',
                'user_id': event.get('user_id')
            }))

    async def broadcast_file_list(self):
        files = await self.get_files()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'send_file_list',
                'files': files
            }
        )

    async def send_file_list(self, event):
        await self.send(text_data=json.dumps({
            'type': 'file_list',
            'files': event['files']
        }))

    @database_sync_to_async
    def get_files(self):
        from .models import WorkspaceNode
        # Optimize: Use select_related for parent to avoid N+1 queries
        nodes = WorkspaceNode.objects.filter(
            workspace_key=self.workspace_key
        ).select_related('parent').order_by('node_type', 'name')
        return [
            {
                'id': node.id,
                'name': node.name,
                'type': node.node_type,
                'parent_id': node.parent.id if node.parent else None,
                'language': node.language
            }
            for node in nodes
        ]

    @database_sync_to_async
    def create_node(self, name, node_type, parent_id):
        from .models import WorkspaceNode
        parent = None
        if parent_id:
            try:
                parent = WorkspaceNode.objects.get(id=parent_id, workspace_key=self.workspace_key)
            except WorkspaceNode.DoesNotExist:
                return None
        
        # Simple language detection based on extension
        language = 'text'
        if node_type == 'file':
            if name.endswith('.py'): language = 'python'
            elif name.endswith('.html'): language = 'html'
            elif name.endswith('.js'): language = 'javascript'
            elif name.endswith('.css'): language = 'css'
            elif name.endswith('.json'): language = 'json'
            elif name.endswith('.md'): language = 'markdown'

        try:
            return WorkspaceNode.objects.create(
                workspace_key=self.workspace_key,
                name=name,
                node_type=node_type,
                parent=parent,
                language=language,
                created_by=self.user
            )
        except Exception as e:
            print(f"Error creating node: {e}")
            return None

    @database_sync_to_async
    def read_file_content(self, node_id):
        from .models import WorkspaceNode
        try:
            node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
            return node.content, node.language
        except WorkspaceNode.DoesNotExist:
            return "", "text"

    @database_sync_to_async
    def update_file_content(self, node_id, content):
        from .models import WorkspaceNode
        try:
            node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
            node.content = content
            node.save()
        except WorkspaceNode.DoesNotExist:
            pass
    
    @database_sync_to_async
    def apply_delta(self, node_id, delta):
        """Apply an incremental delta (insert/delete/replace) to a file."""
        from .models import WorkspaceNode
        try:
            node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
            content = node.content or ''
            position = delta.get('position', 0)
            delta_type = delta.get('type')
            
            if delta_type == 'insert':
                text = delta.get('text', '')
                # Insert text at position
                node.content = content[:position] + text + content[position:]
            elif delta_type == 'delete':
                length = delta.get('length', 0)
                # Delete text at position
                node.content = content[:position] + content[position + length:]
            elif delta_type == 'replace':
                text = delta.get('text', '')
                length = delta.get('length', 0)
                # Replace text at position
                node.content = content[:position] + text + content[position + length:]
            
            node.save()
        except WorkspaceNode.DoesNotExist:
            pass
    
    @database_sync_to_async
    def get_display_name(self):
        return self.user.profile.display_name or self.user.username
    
    @database_sync_to_async
    def get_user_color(self):
        """Generate a consistent color for the user based on their ID."""
        # Simple hash-based color generation
        user_id = self.user.id
        colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8',
            '#F7DC6F', '#BB8FCE', '#85C1E2', '#F8B739', '#52BE80'
        ]
        return colors[user_id % len(colors)]

    @database_sync_to_async
    def delete_node(self, node_id):
        from .models import WorkspaceNode
        try:
            WorkspaceNode.objects.filter(id=node_id, workspace_key=self.workspace_key).delete()
        except Exception:
            pass