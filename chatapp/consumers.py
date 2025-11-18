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
                await self.handle_collab_command(message_content, is_hidden)
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
            user_query = "Summarize our chat so far."
            
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
        messages_queryset = Message.objects.filter(
            (Q(sender=self.user) & Q(receiver=self.contact_user)) |
            (Q(sender=self.contact_user) & Q(receiver=self.user)),
            is_deleted=False
        ).order_by('timestamp')
        return format_chat_history(messages_queryset)

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
                await self.handle_collab_command(message_content, is_hidden)
                return

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
            'timestamp': event['timestamp'],
        }))
        
    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

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
        messages_queryset = self.group.messages.filter(is_deleted=False).order_by('timestamp')
        return format_chat_history(messages_queryset)

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

class WorkspaceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.workspace_key = self.scope['url_route']['kwargs']['workspace_key']
        self.room_group_name = f'workspace_{self.workspace_key}'
        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
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
            node_id = data.get('node_id')
            content = data.get('content')
            if node_id is not None:
                await self.update_file_content(node_id, content)
                # Broadcast update to others, excluding sender if possible, 
                # but for simplicity we broadcast to group and frontend handles it.
                # Ideally, we send a specific 'file_update' event.
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'file_updated',
                        'node_id': node_id,
                        'content': content,
                        'sender_channel_name': self.channel_name
                    }
                )

        elif message_type == 'delete_node':
            node_id = data.get('node_id')
            if node_id:
                await self.delete_node(node_id)
                await self.broadcast_file_list()

    async def file_updated(self, event):
        # Don't echo back to the sender to avoid cursor jumps/conflicts if possible
        if self.channel_name != event.get('sender_channel_name'):
            await self.send(text_data=json.dumps({
                'type': 'file_update',
                'node_id': event['node_id'],
                'content': event['content']
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
        nodes = WorkspaceNode.objects.filter(workspace_key=self.workspace_key).order_by('node_type', 'name')
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
    def delete_node(self, node_id):
        from .models import WorkspaceNode
        try:
            WorkspaceNode.objects.filter(id=node_id, workspace_key=self.workspace_key).delete()
        except Exception:
            pass