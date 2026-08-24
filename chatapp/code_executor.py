import sys
import subprocess
import ast

FORBIDDEN_MODULES = {
    'subprocess', 'shutil', 'pty', 'socket', 'ctypes', 
    'multiprocessing', 'threading', 'signal', 'webbrowser',
    'winreg', 'msvcrt', '_winapi'
}

FORBIDDEN_ATTRS = {
    'system', 'popen', 'spawn', 'kill', 'remove', 'unlink',
    'rmdir', 'removedirs', 'rename', 'replace', 'chmod',
    'environ'
}

def validate_code_safety(code: str) -> tuple[bool, str]:
    """
    Analyzes Python AST to catch destructive system commands and unauthorized access.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"

    for node in ast.walk(tree):
        # Block forbidden imports: import subprocess, from subprocess import Popen
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split('.')[0]
                if root_module in FORBIDDEN_MODULES:
                    return False, f"Security Error: Importing '{alias.name}' is restricted."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split('.')[0]
                if root_module in FORBIDDEN_MODULES:
                    return False, f"Security Error: Importing from '{node.module}' is restricted."

        # Block dangerous attribute calls: os.system, os.remove, os.environ, etc.
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRS:
                return False, f"Security Error: Accessing restricted attribute '{node.attr}'."

        # Block direct invocation of eval, exec, __import__
        elif isinstance(node, ast.Name):
            if node.id in ('eval', 'exec', '__import__'):
                return False, f"Security Error: Using built-in '{node.id}' is restricted."

    return True, ""


def execute_python_code(code: str) -> str:
    """
    Executes the given Python code in an isolated sub-process after passing AST validation.
    """
    if not code or not code.strip():
        return "No code provided to execute."

    is_safe, error_msg = validate_code_safety(code)
    if not is_safe:
        return f"Execution Blocked:\n{error_msg}"

    try:
        process = subprocess.run(
            [sys.executable, "-I", "-s", "-c", code],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = process.stdout
        error = process.stderr
        
        if error:
            return f"Error:\n{error}\nOutput:\n{output}" if output else f"Error:\n{error}"
        return output if output else "Code executed successfully (no output)."

    except subprocess.TimeoutExpired:
        return "Error: Execution timed out (limit: 5 seconds)."
    except Exception as e:
        return f"Execution Error: {str(e)}"
