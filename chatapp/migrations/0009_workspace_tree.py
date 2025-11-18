from django.db import migrations, models
import django.db.models.deletion


def migrate_workspace_files(apps, schema_editor):
    WorkspaceFile = apps.get_model('chatapp', 'WorkspaceFile')
    WorkspaceNode = apps.get_model('chatapp', 'WorkspaceNode')

    for workspace_file in WorkspaceFile.objects.all().iterator():
        position = WorkspaceNode.objects.filter(
            workspace_key=workspace_file.workspace_key,
            parent=None
        ).count()

        WorkspaceNode.objects.create(
            workspace_key=workspace_file.workspace_key,
            name=workspace_file.name,
            node_type='file',
            language=workspace_file.language,
            content=workspace_file.content,
            parent=None,
            position=position,
            created_by=workspace_file.created_by,
            created_at=workspace_file.created_at,
            updated_at=workspace_file.updated_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('chatapp', '0008_merge_20251118_2031'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkspaceNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('workspace_key', models.CharField(db_index=True, max_length=64)),
                ('name', models.CharField(max_length=120)),
                ('node_type', models.CharField(choices=[('file', 'File'), ('folder', 'Folder')], max_length=12)),
                ('language', models.CharField(blank=True, choices=[('python', 'Python'), ('html', 'HTML'), ('javascript', 'JavaScript'), ('css', 'CSS'), ('text', 'Text'), ('json', 'JSON'), ('markdown', 'Markdown')], max_length=20, null=True)),
                ('content', models.TextField(blank=True)),
                ('position', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='workspace_nodes', to='auth.user')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='chatapp.workspacenode')),
            ],
            options={
                'ordering': ['position', 'name'],
                'unique_together': {('workspace_key', 'parent', 'name')},
            },
        ),
        migrations.RunPython(migrate_workspace_files, reverse_code=migrations.RunPython.noop),
        migrations.DeleteModel(
            name='WorkspaceFile',
        ),
    ]

