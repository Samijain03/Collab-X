import sys
import subprocess
import io
import contextlib

def execute_python_code(code):
    """
    Executes the given Python code and returns the output.
    WARNING: This is a basic implementation and should be sandboxed in production.
    """
    # Create a string buffer to capture stdout
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        # We will use subprocess to run the code in a separate process
        # This is slightly safer than exec() in the main process, but still not fully sandboxed.
        # We pass the code as a string to the python executable.
        
        process = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=5  # 5 second timeout to prevent infinite loops
        )
        
        output = process.stdout
        error = process.stderr
        
        if error:
            return f"Error:\n{error}\nOutput:\n{output}"
        return output if output else "Code executed successfully (no output)."

    except subprocess.TimeoutExpired:
        return "Error: Execution timed out (limit: 5 seconds)."
    except Exception as e:
        return f"Execution Error: {str(e)}"
