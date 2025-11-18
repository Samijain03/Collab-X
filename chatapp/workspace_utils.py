from __future__ import annotations

import os
from typing import Optional, Dict, Any

from django.db import transaction

from django.contrib.auth import get_user_model
from .models import WorkspaceNode

User = get_user_model()


LANGUAGE_BY_EXTENSION = {
    '.py': 'python',
    '.html': 'html',
    '.htm': 'html',
    '.js': 'javascript',
    '.css': 'css',
    '.json': 'json',
    '.md': 'markdown',
    '.txt': 'text',
}

DEFAULT_TEMPLATES = {
    'python': """def main():
    print("Hello from {filename}!")


if __name__ == "__main__":
    main()
""",
    'html': """<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{filename}</title>
  </head>
  <body>
    <h1>Hello from {filename}</h1>
  </body>
</html>
""",
    'javascript': 'console.log("Hello from {filename}!");\n',
    'css': "/* {filename} */\n",
    'json': "{\n  \"message\": \"Hello from {filename}!\"\n}\n",
    'markdown': "# {filename}\n",
    'text': "",
}


def normalize_path(path: str) -> str:
    return "/".join([segment for segment in path.strip().replace("\\", "/").split("/") if segment])


def guess_language(filename: str, fallback: str = 'text') -> str:
    _, ext = os.path.splitext(filename.lower())
    return LANGUAGE_BY_EXTENSION.get(ext, fallback)


@transaction.atomic
def ensure_path(
    workspace_key: str,
    path: str,
    *,
    user: User,
    node_type: str = WorkspaceNode.NodeType.FILE,
    language: Optional[str] = None,
    content: Optional[str] = None,
) -> WorkspaceNode:
    """
    Ensure that the given path exists (creating intermediate folders as needed)
    and return the final node.
    """
    normalized = normalize_path(path)
    if not normalized:
        raise ValueError("Path cannot be empty.")

    segments = normalized.split("/")
    parent = None

    for segment in segments[:-1]:
        parent = WorkspaceNode.objects.get_or_create(
            workspace_key=workspace_key,
            name=segment,
            parent=parent,
            defaults={
                'node_type': WorkspaceNode.NodeType.FOLDER,
                'created_by': user,
                'position': WorkspaceNode.objects.filter(workspace_key=workspace_key, parent=parent).count(),
            }
        )[0]

    final_name = segments[-1]
    defaults = {
        'node_type': node_type,
        'created_by': user,
        'position': WorkspaceNode.objects.filter(workspace_key=workspace_key, parent=parent).count(),
    }

    if node_type == WorkspaceNode.NodeType.FILE:
        resolved_language = language or guess_language(final_name, fallback='text')
        defaults['language'] = resolved_language
        defaults['content'] = content if content is not None else DEFAULT_TEMPLATES.get(
            resolved_language, ''
        ).format(filename=final_name)
    else:
        defaults['language'] = None
        defaults['content'] = ''

    node, created = WorkspaceNode.objects.get_or_create(
        workspace_key=workspace_key,
        name=final_name,
        parent=parent,
        defaults=defaults
    )

    if not created and node_type == WorkspaceNode.NodeType.FILE and content is not None:
        node.content = content
        node.language = defaults['language']
        node.save(update_fields=['content', 'language', 'updated_at'])

    return node


def serialize_node(node: WorkspaceNode) -> Dict[str, Any]:
    return {
        'id': node.id,
        'name': node.name,
        'node_type': node.node_type,
        'parent_id': node.parent_id,
        'language': node.language,
        'content': node.content if node.is_file else '',
        'position': node.position,
        'updated_at': node.updated_at.isoformat(),
        'full_path': node.full_path,
    }


def delete_subtree(node: WorkspaceNode) -> int:
    """Delete a node and all descendants. Returns number of nodes deleted."""
    descendants = WorkspaceNode.objects.filter(parent=node)
    for child in descendants:
        delete_subtree(child)
    deleted, _ = node.delete()
    return deleted


def parse_collab_command(command_text: str) -> tuple[Optional[str], Optional[str], str, Optional[str]]:
    """
    Parse /Collab command to extract file/folder path and instructions.
    Returns: (target_type, target_path, instructions, language)
    target_type: 'file', 'folder', or None
    """
    import re
    
    # Pattern: /Collab [file|folder] path: instructions
    # Or: /Collab file path/to/file.py language: instructions
    file_pattern = r'/Collab\s+file\s+([^\s:]+)(?:\s+(\w+):)?\s*:?\s*(.*)'
    folder_pattern = r'/Collab\s+folder\s+([^\s:]+)\s*:?\s*(.*)'
    
    file_match = re.match(file_pattern, command_text, re.IGNORECASE)
    if file_match:
        path = file_match.group(1).strip()
        language = file_match.group(2) if file_match.group(2) else None
        instructions = file_match.group(3).strip()
        return ('file', path, instructions, language)
    
    folder_match = re.match(folder_pattern, command_text, re.IGNORECASE)
    if folder_match:
        path = folder_match.group(1).strip()
        instructions = folder_match.group(2).strip()
        return ('folder', path, instructions, None)
    
    return (None, None, command_text.replace('/Collab', '').strip(), None)


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    """
    Extract code blocks from AI response.
    Returns list of {filename, language, content}
    """
    import re
    
    blocks = []
    
    # Pattern: ```language:filename or ```filename or ```language
    pattern = r'```(?:(\w+)(?::([^\n]+))?|([^\n]+))?\n(.*?)```'
    
    for match in re.finditer(pattern, text, re.DOTALL):
        lang = match.group(1) or match.group(3) or 'text'
        filename = match.group(2) or None
        content = match.group(4).strip()
        
        if content:
            blocks.append({
                'filename': filename,
                'language': lang.lower(),
                'content': content
            })
    
    # If no code blocks but text looks like code, treat entire response as code
    if not blocks and text.strip():
        # Check if it looks like code (has indentation, keywords, etc.)
        lines = text.strip().split('\n')
        if len(lines) > 3 or any(line.strip().startswith(('def ', 'class ', 'import ', 'from ', '<!', 'function ', 'const ', 'let ')) for line in lines[:5]):
            blocks.append({
                'filename': None,
                'language': 'text',
                'content': text.strip()
            })
    
    return blocks