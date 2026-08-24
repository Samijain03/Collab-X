from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Profile, Message, Group, GroupMessage, ContactRequest, WorkspaceNode
from .workspace_utils import ensure_path, guess_language, normalize_path
from .code_executor import execute_python_code, validate_code_safety


class ProfileAndAuthTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='password123')
        self.user2 = User.objects.create_user(username='bob', password='password123')

    def test_profile_auto_creation(self):
        """Test that a profile is automatically created via post_save signal."""
        self.assertIsNotNone(self.user1.profile)
        self.assertEqual(str(self.user1.profile), 'alice')

    def test_profile_display_name(self):
        self.user1.profile.display_name = 'Alice W.'
        self.user1.profile.save()
        self.assertEqual(self.user1.profile.display_name, 'Alice W.')


class ContactRequestTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(username='alice', password='password123')
        self.bob = User.objects.create_user(username='bob', password='password123')

    def test_send_contact_request(self):
        self.client.login(username='alice', password='password123')
        response = self.client.get(f'/send-request/{self.bob.id}/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ContactRequest.objects.filter(from_user=self.alice, to_user=self.bob).exists())

    def test_mutual_contact_request_auto_accepts(self):
        """If Bob requested Alice, and Alice sends a request to Bob, they should become contacts immediately."""
        ContactRequest.objects.create(from_user=self.bob, to_user=self.alice)
        self.client.login(username='alice', password='password123')
        response = self.client.get(f'/send-request/{self.bob.id}/')
        
        self.assertFalse(ContactRequest.objects.filter(from_user=self.bob, to_user=self.alice).exists())
        self.assertTrue(self.alice.profile.contacts.filter(user=self.bob).exists())
        self.assertTrue(self.bob.profile.contacts.filter(user=self.alice).exists())


class GroupChatTestCase(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='admin_user', password='password123')
        self.member = User.objects.create_user(username='team_member', password='password123')
        self.group = Group.objects.create(name='Dev Team', creator=self.creator)
        self.group.members.add(self.creator, self.member)

    def test_group_membership(self):
        self.assertEqual(self.group.members.count(), 2)
        self.assertTrue(self.group.members.filter(id=self.creator.id).exists())
        self.assertTrue(self.group.members.filter(id=self.member.id).exists())

    def test_group_message_creation(self):
        msg = GroupMessage.objects.create(group=self.group, sender=self.creator, content="Hello team!")
        self.assertEqual(msg.content, "Hello team!")
        self.assertIn("Hello team!", str(msg))


class WorkspaceUtilsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='coder', password='password123')
        self.workspace_key = 'chat_1_2'

    def test_language_detection(self):
        self.assertEqual(guess_language('main.py'), 'python')
        self.assertEqual(guess_language('index.html'), 'html')
        self.assertEqual(guess_language('app.js'), 'javascript')
        self.assertEqual(guess_language('style.css'), 'css')
        self.assertEqual(guess_language('data.json'), 'json')
        self.assertEqual(guess_language('unknown.xyz'), 'text')

    def test_path_normalization(self):
        self.assertEqual(normalize_path('/src/utils/file.py'), 'src/utils/file.py')
        self.assertEqual(normalize_path('src\\utils\\file.py'), 'src/utils/file.py')

    def test_ensure_path_nested(self):
        node = ensure_path(
            workspace_key=self.workspace_key,
            path='backend/api/views.py',
            user=self.user,
            node_type=WorkspaceNode.NodeType.FILE
        )
        self.assertEqual(node.name, 'views.py')
        self.assertEqual(node.full_path, 'backend/api/views.py')
        self.assertEqual(node.language, 'python')
        
        # Verify parent structure
        self.assertEqual(node.parent.name, 'api')
        self.assertEqual(node.parent.parent.name, 'backend')


class CodeExecutorSafetyTestCase(TestCase):
    def test_safe_execution(self):
        result = execute_python_code('print(2 + 2)')
        self.assertIn('4', result)

    def test_blocked_subprocess(self):
        is_safe, msg = validate_code_safety('import subprocess\nsubprocess.run(["ls"])')
        self.assertFalse(is_safe)
        self.assertIn("Security Error", msg)

    def test_blocked_os_system(self):
        is_safe, msg = validate_code_safety('import os\nos.system("echo hacked")')
        self.assertFalse(is_safe)
        self.assertIn("Security Error", msg)

    def test_blocked_eval(self):
        is_safe, msg = validate_code_safety('eval("__import__(\'os\').system(\'ls\')")')
        self.assertFalse(is_safe)


class WorkspaceZipExportAndAITestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(username='alice', password='password123')
        self.bob = User.objects.create_user(username='bob', password='password123')
        self.alice.profile.contacts.add(self.bob.profile)
        self.bob.profile.contacts.add(self.alice.profile)
        
        user_ids = sorted([self.alice.id, self.bob.id])
        self.workspace_key = f"chat_{user_ids[0]}_{user_ids[1]}"
        
        # Create test nodes
        ensure_path(
            workspace_key=self.workspace_key,
            path='src/main.py',
            user=self.alice,
            content='print("Hello Alice & Bob")'
        )

    def test_export_workspace_zip(self):
        import zipfile
        import io

        self.client.login(username='alice', password='password123')
        response = self.client.get(f'/workspace/{self.workspace_key}/export-zip/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

        # Verify zip content
        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            namelist = zf.namelist()
            self.assertIn('src/main.py', namelist)
            file_content = zf.read('src/main.py').decode('utf-8')
            self.assertIn('Hello Alice & Bob', file_content)

    def test_parse_collab_command_file(self):
        from .workspace_utils import parse_collab_command, extract_code_blocks
        cmd = "/Collab file backend/server.py python: create a fastapi server"
        target_type, path, instructions, lang = parse_collab_command(cmd)
        self.assertEqual(target_type, 'file')
        self.assertEqual(path, 'backend/server.py')
        self.assertEqual(instructions, 'create a fastapi server')

    def test_extract_code_blocks(self):
        from .workspace_utils import extract_code_blocks
        markdown_text = "Here is the code:\n```python:utils.py\ndef add(a, b):\n    return a + b\n```\nEnjoy!"
        blocks = extract_code_blocks(markdown_text)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['language'], 'python')
        self.assertIn('def add(a, b):', blocks[0]['content'])

