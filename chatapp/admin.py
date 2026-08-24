from django.contrib import admin
from .models import Profile, Message, ContactRequest, Group, GroupMessage, WorkspaceNode


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'display_name', 'contacts_count')
    search_fields = ('user__username', 'display_name', 'about_me')

    def contacts_count(self, obj):
        return obj.contacts.count()
    contacts_count.short_description = 'Contacts'


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'short_content', 'has_file', 'timestamp', 'is_deleted')
    list_filter = ('is_deleted', 'timestamp')
    search_fields = ('sender__username', 'receiver__username', 'content', 'file_name')
    date_hierarchy = 'timestamp'

    def short_content(self, obj):
        return obj.content[:50] if obj.content else '(Attachment)'
    short_content.short_description = 'Content'

    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_user', 'to_user', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('from_user__username', 'to_user__username')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'creator', 'member_count', 'created_at')
    search_fields = ('name', 'creator__username')
    list_filter = ('created_at',)
    filter_horizontal = ('members',)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'


@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'group', 'sender', 'short_content', 'has_file', 'timestamp', 'is_deleted')
    list_filter = ('group', 'is_deleted', 'timestamp')
    search_fields = ('group__name', 'sender__username', 'content', 'file_name')
    date_hierarchy = 'timestamp'

    def short_content(self, obj):
        return obj.content[:50] if obj.content else '(Attachment)'
    short_content.short_description = 'Content'

    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'


@admin.register(WorkspaceNode)
class WorkspaceNodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'workspace_key', 'node_type', 'language', 'parent', 'created_by', 'updated_at')
    list_filter = ('node_type', 'language', 'workspace_key')
    search_fields = ('name', 'workspace_key', 'created_by__username')
