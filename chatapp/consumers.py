# chatapp/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
# --- UPDATED IMPORTS ---
from .models import Message, Profile, Group, GroupMessage

class ChatConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        try:
            # 1. Get user and contact_id from the URL
            self.user = self.scope['user']
            self.contact_id = self.scope['url_route']['kwargs']['contact_id']
            
            # 2. Check if user is authenticated
            if not self.user.is_authenticated:
                print(f"[WebSocket] REJECT: User is not authenticated.")
                await self.close()
                return
                
            print(f"[WebSocket] INFO: User '{self.user.username}' attempting to connect to chat with user_id '{self.contact_id}'.")

            # 3. Get the contact user object
            self.contact_user = await self.get_user(self.contact_id)
            
            # 4. Get profiles
            self.contact_profile = await self.get_profile(self.contact_user)
            self.user_profile = await self.get_profile(self.user)
            
            # 5. Security Check: Ensure they are contacts
            are_contacts = await self.check_contacts(self.user_profile, self.contact_user)
            if not are_contacts:
                print(f"[WebSocket] REJECT: User '{self.user.username}' and '{self.contact_user.username}' are not contacts.")
                await self.close()
                return

        except User.DoesNotExist:
            print(f"[WebSocket] ERROR: User with id={self.contact_id} does not exist.")
            await self.close()
            return
        except Profile.DoesNotExist:
            print(f"[WebSocket] ERROR: A Profile is missing for user '{self.user.username}' or contact '{self.contact_user.username}'.")
            await self.close()
            return
        except Exception as e:
            print(f"[WebSocket] ERROR: An unexpected error occurred: {e}")
            await self.close()
            return
            
        # 6. Create a unique, private room name for the pair
        user_ids = sorted([self.user.id, self.contact_user.id])
        self.room_group_name = f'chat_{user_ids[0]}_{user_ids[1]}'

        # 7. Join the room
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # 8. Accept the connection
        print(f"[WebSocket] ACCEPT: Connection accepted for '{self.user.username}' to room '{self.room_group_name}'.")
        await self.accept()


    async def disconnect(self, close_code):
        # Leave the room
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Receive message from WebSocket (frontend JavaScript)
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_content = data['message']

        if not message_content.strip():
            return # Don't send empty messages

        # 1. Save the new message to the database
        new_message = await self.save_message(
            sender=self.user,
            receiver=self.contact_user,
            content=message_content
        )

        # 2. Broadcast the message to the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message', # This calls the 'chat_message' method
                'message': new_message.content,
                'sender_username': self.user.username,
                'timestamp': new_message.timestamp.strftime("%I:%M %p") # 12-hr format
            }
        )

    # Receive message from room group (broadcast)
    async def chat_message(self, event):
        # This method is called when a message is broadcast to the group
        
        # Send message data to the WebSocket (client)
        await self.send(text_data=json.dumps({
            'content': event['message'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
        }))

    # --- DATABASE HELPER FUNCTIONS ---
    
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
        return Message.objects.create(
            sender=sender,
            receiver=receiver,
            content=content
        )


# --- ADD THIS ENTIRE NEW CLASS FOR GROUP CHAT ---

class GroupChatConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        try:
            self.user = self.scope['user']
            self.group_id = self.scope['url_route']['kwargs']['group_id']

            if not self.user.is_authenticated:
                print("[WebSocket] REJECT: User is not authenticated.")
                await self.close()
                return

            print(f"[WebSocket] INFO: User '{self.user.username}' attempting to connect to group '{self.group_id}'.")

            # Get the group and check if the user is a member
            self.group = await self.get_group(self.group_id)
            is_member = await self.check_membership(self.group, self.user)

            if not is_member:
                print(f"[WebSocket] REJECT: User '{self.user.username}' is not a member of group '{self.group_id}'.")
                await self.close()
                return
        
        except Group.DoesNotExist:
            print(f"[WebSocket] ERROR: Group with id={self.group_id} does not exist.")
            await self.close()
            return
        except Exception as e:
            print(f"[WebSocket] ERROR: An unexpected error occurred: {e}")
            await self.close()
            return

        # Set the room name
        self.room_group_name = f'group_{self.group_id}'

        # Join the room
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Accept the connection
        print(f"[WebSocket] ACCEPT: Connection accepted for '{self.user.username}' to room '{self.room_group_name}'.")
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        message_content = data['message']

        if not message_content.strip():
            return

        # Save the new group message
        new_message = await self.save_group_message(
            group=self.group,
            sender=self.user,
            content=message_content
        )

        # Broadcast the message to the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'group_chat_message',
                'message': new_message.content,
                'sender_username': self.user.username,
                'timestamp': new_message.timestamp.strftime("%I:%M %p")
            }
        )

    # Receive message from room group
    async def group_chat_message(self, event):
        await self.send(text_data=json.dumps({
            'content': event['message'],
            'sender_username': event['sender_username'],
            'timestamp': event['timestamp'],
        }))

    # --- Database Helpers for Group ---
    @database_sync_to_async
    def get_group(self, group_id):
        return Group.objects.get(id=group_id)

    @database_sync_to_async
    def check_membership(self, group, user):
        return group.members.filter(id=user.id).exists()

    @database_sync_to_async
    def save_group_message(self, group, sender, content):
        return GroupMessage.objects.create(
            group=group,
            sender=sender,
            content=content
        )