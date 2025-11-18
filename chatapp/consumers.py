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