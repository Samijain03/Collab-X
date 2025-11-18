# chatapp/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    contacts = models.ManyToManyField('self', related_name='contact_of', symmetrical=False, blank=True)
    
 # --- add by kk ---
    display_name = models.CharField(max_length=50, blank=True, null=True)
    about_me = models.TextField(max_length=200, blank=True)
    profile_picture = models.ImageField(default='profile_pics/default.jpg', upload_to='profile_pics')

    def __str__(self):
        return self.user.username

# ... (keep the Profile signals as they are) ...

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class Message(models.Model):
    # ... (keep the Message model as it is) ...
    sender = models.ForeignKey(User, related_name="sent_messages", on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name="received_messages", on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    def __str__(self):
        return f"From {self.sender.username} to {self.receiver.username}"

    class Meta:
        ordering = ['timestamp']

# --- ADD THIS NEW MODEL ---
class ContactRequest(models.Model):
    """Model to represent a pending contact request."""
    from_user = models.ForeignKey(User, related_name='sent_contact_requests', on_delete=models.CASCADE)
    to_user = models.ForeignKey(User, related_name='received_contact_requests', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Request from {self.from_user.username} to {self.to_user.username}"

    class Meta:
        # Ensures a user can only send one request to another user at a time
        unique_together = ('from_user', 'to_user')

# --- ADD THESE NEW MODELS FOR GROUP CHAT ---

class Group(models.Model):
    name = models.CharField(max_length=100)
    members = models.ManyToManyField(User, related_name='chat_groups')
    creator = models.ForeignKey(User, related_name='created_groups', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class GroupMessage(models.Model):
    group = models.ForeignKey(Group, related_name='messages', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='group_messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f'{self.sender.username} in {self.group.name}: {self.content[:20]}'