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

from .models import Message, Profile, Group, GroupMessage, WorkspaceNode
from .gemini_utils import format_chat_history, get_collab_response
from .workspace_utils import (
    ensure_path,
    serialize_node,
    parse_collab_command,
    extract_code_blocks,
    delete_subtree,
    normalize_path,
    guess_language,
)

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

    # --- UPDATED `handle_collab_command` with workspace integration ---
    async def handle_collab_command(self, command_text, is_hidden):
        request_id = f"bot-{self.user.id}-{int(time.time())}"
        
        # Parse command to check if it's a file/folder operation
        target_type, target_path, instructions, language = await database_sync_to_async(parse_collab_command)(command_text)
        
        # Get workspace key for this chat
        user_ids = sorted([self.user.id, self.contact_user.id])
        workspace_key = f"chat_{user_ids[0]}_{user_ids[1]}"
        
        # Send "Thinking..." message
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
        
        # Prepare query for Gemini
        if target_type:
            # File/folder operation - enhance prompt
            user_query = f"Create/update {target_type} at {target_path}. Instructions: {instructions}" if instructions else f"Create/update {target_type} at {target_path}"
            if target_type == 'file' and language:
                user_query += f" Language: {language}"
            user_query += "\n\nPlease provide the code in a code block. If creating multiple files, use separate code blocks with filename annotations like: ```python:filename.py"
        else:
            # Regular query
            if is_hidden:
                user_query = command_text.replace('/Collab hidden', '').strip()
            else:
                user_query = command_text.replace('/Collab', '').strip()
            if not user_query:
                user_query = "Summarize our chat so far."
        
        # Get chat history and workspace context
        chat_history_string = await self.get_chat_history()
        workspace_files = await self.get_workspace_files(workspace_key)
        
        # Build enhanced prompt with workspace context
        workspace_context = ""
        if workspace_files:
            workspace_context = "\n\nCurrent workspace files:\n" + "\n".join([f"- {f['full_path']} ({f.get('language', 'text')})" for f in workspace_files[:10]])
        
        # Call Gemini with enhanced context
        enhanced_query = user_query + workspace_context
        bot_response_text = await database_sync_to_async(get_collab_response)(
            chat_history_string, 
            enhanced_query
        )
        clean_content, jump_id = parse_bot_response(bot_response_text)
        
        # If it's a file/folder operation, extract code and create/update files
        created_files = []
        if target_type and target_path:
            code_blocks = await database_sync_to_async(extract_code_blocks)(bot_response_text)
            
            if target_type == 'file':
                # Single file operation
                if code_blocks:
                    block = code_blocks[0]
                    file_path = target_path
                    file_lang = language or block.get('language') or await database_sync_to_async(guess_language)(file_path)
                    file_content = block.get('content', clean_content)
                    
                    node = await database_sync_to_async(ensure_path)(
                        workspace_key,
                        file_path,
                        user=self.user,
                        node_type=WorkspaceNode.NodeType.FILE,
                        language=file_lang,
                        content=file_content
                    )
                    created_files.append(node.id)
                    
                    # Broadcast workspace update
                    await self.broadcast_workspace_update(workspace_key, node.id)
            elif target_type == 'folder':
                # Multiple files in folder
                for block in code_blocks:
                    filename = block.get('filename')
                    if not filename:
                        continue
                    file_path = f"{target_path.rstrip('/')}/{filename}"
                    file_lang = block.get('language') or await database_sync_to_async(guess_language)(filename)
                    file_content = block.get('content', '')
                    
                    node = await database_sync_to_async(ensure_path)(
                        workspace_key,
                        file_path,
                        user=self.user,
                        node_type=WorkspaceNode.NodeType.FILE,
                        language=file_lang,
                        content=file_content
                    )
                    created_files.append(node.id)
                
                if created_files:
                    await self.broadcast_workspace_update(workspace_key, created_files[-1])
        
        # Send final response with file creation info
        response_content = clean_content
        if created_files:
            response_content += f"\n\n✅ Created/updated {len(created_files)} file(s) in workspace."
        
        final_payload_js = {
            'type': 'bot_message',
            'status': 'complete',
            'content': response_content,
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
                'message': response_content,
                'sender_username': 'Collab-X',
                'jump_id': jump_id,
                'request_id': request_id
            })
    
    async def broadcast_workspace_update(self, workspace_key, active_id):
        """Broadcast workspace tree refresh"""
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        nodes = await self.get_workspace_nodes(workspace_key)
        await channel_layer.group_send(workspace_key, {
            'type': 'workspace_event',
            'event': 'tree_refresh',
            'nodes': nodes,
            'active_id': active_id,
        })
    
    @database_sync_to_async
    def get_workspace_files(self, workspace_key):
        """Get list of workspace files for context"""
        nodes = WorkspaceNode.objects.filter(workspace_key=workspace_key, node_type=WorkspaceNode.NodeType.FILE)
        return [serialize_node(node) for node in nodes[:20]]
    
    @database_sync_to_async
    def get_workspace_nodes(self, workspace_key):
        """Get all workspace nodes"""
        nodes = WorkspaceNode.objects.filter(workspace_key=workspace_key).select_related('parent').order_by('parent_id', 'position', 'name')
        return [serialize_node(node) for node in nodes]

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
        
        # Parse command to check if it's a file/folder operation
        target_type, target_path, instructions, language = await database_sync_to_async(parse_collab_command)(command_text)
        
        # Get workspace key for this group
        workspace_key = f"group_{self.group_id}"
        
        # Send "Thinking..." message
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
        
        # Prepare query for Gemini
        if target_type:
            user_query = f"Create/update {target_type} at {target_path}. Instructions: {instructions}" if instructions else f"Create/update {target_type} at {target_path}"
            if target_type == 'file' and language:
                user_query += f" Language: {language}"
            user_query += "\n\nPlease provide the code in a code block. If creating multiple files, use separate code blocks with filename annotations like: ```python:filename.py"
        else:
            if is_hidden:
                user_query = command_text.replace('/Collab hidden', '').strip()
            else:
                user_query = command_text.replace('/Collab', '').strip()
            if not user_query:
                user_query = "Summarize this group chat so far."
        
        # Get chat history and workspace context
        chat_history_string = await self.get_chat_history()
        workspace_files = await self.get_workspace_files(workspace_key)
        
        workspace_context = ""
        if workspace_files:
            workspace_context = "\n\nCurrent workspace files:\n" + "\n".join([f"- {f['full_path']} ({f.get('language', 'text')})" for f in workspace_files[:10]])
        
        enhanced_query = user_query + workspace_context
        bot_response_text = await database_sync_to_async(get_collab_response)(
            chat_history_string, 
            enhanced_query
        )
        clean_content, jump_id = parse_bot_response(bot_response_text)
        
        # If it's a file/folder operation, extract code and create/update files
        created_files = []
        if target_type and target_path:
            code_blocks = await database_sync_to_async(extract_code_blocks)(bot_response_text)
            
            if target_type == 'file':
                if code_blocks:
                    block = code_blocks[0]
                    file_path = target_path
                    file_lang = language or block.get('language') or await database_sync_to_async(guess_language)(file_path)
                    file_content = block.get('content', clean_content)
                    
                    node = await database_sync_to_async(ensure_path)(
                        workspace_key,
                        file_path,
                        user=self.user,
                        node_type=WorkspaceNode.NodeType.FILE,
                        language=file_lang,
                        content=file_content
                    )
                    created_files.append(node.id)
                    await self.broadcast_workspace_update(workspace_key, node.id)
            elif target_type == 'folder':
                for block in code_blocks:
                    filename = block.get('filename')
                    if not filename:
                        continue
                    file_path = f"{target_path.rstrip('/')}/{filename}"
                    file_lang = block.get('language') or await database_sync_to_async(guess_language)(filename)
                    file_content = block.get('content', '')
                    
                    node = await database_sync_to_async(ensure_path)(
                        workspace_key,
                        file_path,
                        user=self.user,
                        node_type=WorkspaceNode.NodeType.FILE,
                        language=file_lang,
                        content=file_content
                    )
                    created_files.append(node.id)
                
                if created_files:
                    await self.broadcast_workspace_update(workspace_key, created_files[-1])
        
        response_content = clean_content
        if created_files:
            response_content += f"\n\n✅ Created/updated {len(created_files)} file(s) in workspace."
        
        final_payload_js = {
            'type': 'bot_message',
            'status': 'complete',
            'content': response_content,
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
                'message': response_content,
                'sender_username': 'Collab-X',
                'jump_id': jump_id,
                'request_id': request_id
            })
    
    async def broadcast_workspace_update(self, workspace_key, active_id):
        """Broadcast workspace tree refresh"""
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        nodes = await self.get_workspace_nodes(workspace_key)
        await channel_layer.group_send(workspace_key, {
            'type': 'workspace_event',
            'event': 'tree_refresh',
            'nodes': nodes,
            'active_id': active_id,
        })
    
    @database_sync_to_async
    def get_workspace_files(self, workspace_key):
        """Get list of workspace files for context"""
        nodes = WorkspaceNode.objects.filter(workspace_key=workspace_key, node_type=WorkspaceNode.NodeType.FILE)
        return [serialize_node(node) for node in nodes[:20]]
    
    @database_sync_to_async
    def get_workspace_nodes(self, workspace_key):
        """Get all workspace nodes"""
        nodes = WorkspaceNode.objects.filter(workspace_key=workspace_key).select_related('parent').order_by('parent_id', 'position', 'name')
        return [serialize_node(node) for node in nodes]

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

        nodes = await self.get_workspace_nodes()
        await self.send(text_data=json.dumps({
            'type': 'workspace_bootstrap',
            'nodes': nodes
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'workspace_key'):
            await self.channel_layer.group_discard(self.workspace_key, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'create_entry':
            await self.handle_create_entry(data)
        elif action == 'create_batch':
            await self.handle_create_batch(data)
        elif action == 'rename_node':
            await self.handle_rename_node(data)
        elif action == 'move_node':
            await self.handle_move_node(data)
        elif action == 'delete_node':
            await self.handle_delete_node(data)
        elif action == 'update_content':
            await self.handle_update_content(data)
        elif action == 'run_file':
            await self.handle_run_file(data)

    async def handle_create_entry(self, data):
        path = (data.get('path') or '').strip()
        node_type = data.get('node_type', WorkspaceNode.NodeType.FILE)
        language = data.get('language')
        content = data.get('content')

        if not path:
            return

        node = await database_sync_to_async(ensure_path)(
            self.workspace_key,
            path,
            user=self.user,
            node_type=node_type,
            language=language,
            content=content
        )
        await self.broadcast_tree(active_id=node.id if node.is_file else None)

    async def handle_create_batch(self, data):
        entries = data.get('entries') or []
        created_ids = []
        for entry in entries:
            path = entry.get('path')
            if not path:
                continue
            node = await database_sync_to_async(ensure_path)(
                self.workspace_key,
                path,
                user=self.user,
                node_type=entry.get('node_type', WorkspaceNode.NodeType.FILE),
                language=entry.get('language'),
                content=entry.get('content')
            )
            created_ids.append(node.id)
        if created_ids:
            await self.broadcast_tree(active_id=created_ids[-1])

    async def handle_rename_node(self, data):
        node_id = data.get('node_id')
        new_name = (data.get('name') or '').strip()
        if not node_id or not new_name:
            return
        await database_sync_to_async(self._rename_node)(node_id, new_name)
        await self.broadcast_tree(active_id=node_id)

    async def handle_move_node(self, data):
        node_id = data.get('node_id')
        parent_id = data.get('parent_id')
        position = data.get('position', 0)
        if not node_id:
            return
        await database_sync_to_async(self._move_node)(node_id, parent_id, position)
        await self.broadcast_tree(active_id=node_id)

    async def handle_delete_node(self, data):
        node_id = data.get('node_id')
        if not node_id:
            return
        await database_sync_to_async(self._delete_node)(node_id)
        await self.broadcast_tree()

    async def handle_update_content(self, data):
        node_id = data.get('node_id')
        content = data.get('content', '')
        if not node_id:
            return
        await database_sync_to_async(self._update_file_content)(node_id, content)
        await self.broadcast_tree(active_id=node_id)

    async def handle_run_file(self, data):
        node_id = data.get('node_id')
        node = await self.get_workspace_node(node_id)
        if not node or node['node_type'] != WorkspaceNode.NodeType.FILE:
            return

        if node['language'] == 'python':
            result = await sync_to_async(self._run_python)(node['content'])
        else:
            result = {
                'stdout': '',
                'stderr': '',
                'html': node['content']
            }

        response = {
            'type': 'workspace_event',
            'event': 'run_result',
            'node_id': node_id,
            'language': node['language'],
            'requested_by': self.user.username,
            'result': result
        }

        await self.channel_layer.group_send(self.workspace_key, response)

    async def workspace_event(self, event):
        if event.get('event') == 'tree_refresh':
            await self.send(text_data=json.dumps(event))
        else:
            await self.send(text_data=json.dumps(event))

    async def broadcast_tree(self, active_id: int | None = None):
        nodes = await self.get_workspace_nodes()
        payload = {
            'type': 'workspace_event',
            'event': 'tree_refresh',
            'nodes': nodes,
            'active_id': active_id,
        }
        await self.channel_layer.group_send(self.workspace_key, payload)

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
    def get_workspace_nodes(self):
        nodes = WorkspaceNode.objects.filter(workspace_key=self.workspace_key).select_related('parent').order_by('parent_id', 'position', 'name')
        return [serialize_node(node) for node in nodes]

    @database_sync_to_async
    def _rename_node(self, node_id, new_name):
        node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
        node.name = new_name
        node.save(update_fields=['name', 'updated_at'])

    @database_sync_to_async
    def _move_node(self, node_id, parent_id, position):
        node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
        parent = None
        if parent_id:
            parent = WorkspaceNode.objects.get(id=parent_id, workspace_key=self.workspace_key)
        node.parent = parent
        node.position = position or 0
        node.save(update_fields=['parent', 'position', 'updated_at'])

    @database_sync_to_async
    def _delete_node(self, node_id):
        node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
        delete_subtree(node)

    @database_sync_to_async
    def _update_file_content(self, node_id, content):
        node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key, node_type=WorkspaceNode.NodeType.FILE)
        node.content = content
        node.save(update_fields=['content', 'updated_at'])

    @database_sync_to_async
    def get_workspace_node(self, node_id):
        try:
            node = WorkspaceNode.objects.get(id=node_id, workspace_key=self.workspace_key)
            return serialize_node(node)
        except WorkspaceNode.DoesNotExist:
            return None

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