
from ollama import chat, ChatResponse
import os
import subprocess
import json
import shlex
from prompt_toolkit import prompt

messages = []
user_state = {"name": "user"}
model = "llama3.2:3b"


# Python functions that the model calls

def set_user_name(name):
    user_state["name"] = name
    return {"success": True, "name": name}


def make_directory(path):
    try:
        os.mkdir(path)
        return f"Directory created: {path}"
    except OSError as error:
        raise RuntimeError(f"Error creating directory: {error}")


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as error:
        raise RuntimeError(f"Error reading {path}: {error}")


def write_file(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File saved: {path}, {len(content)} characters"
    except OSError as error:
        raise RuntimeError(f"Error writing {path}: {error}")


def append_file(path, content):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"File updated: {path}, {len(content)} characters added"
    except OSError as error:
        raise RuntimeError(f"Error appending to {path}: {error}")


def list_files(path="."):
    try:
        entries = []
        for entry in os.scandir(path):
            if entry.is_dir() or entry.is_file():
                entries.append(entry.name)

        return "\n".join(sorted(entries)) or "Empty directory!"

    except OSError as error:
        raise RuntimeError(f"Error listing {path}: {error}")


def run_commands(command):
    print("\nWARNING: COMMAND REQUESTED BY MODEL")
    print(command)

    answer = input(
        "Run this command? [Y/N]: "
    )

    if answer.strip().lower() != "y":
        return "The user declined to run this command."

    # Safer than shell=True: no shell interpretation.
    # Complex shell syntax (pipes, redirection, etc.)
    # is intentionally unsupported.
    try:
        args = shlex.split(command, posix=(os.name != "nt"))

        if not args:
            return "No command provided."

        result = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60
        )

        output = (result.stdout + result.stderr).strip()

        return {
            "exit_code": result.returncode,
            "output": output or "(No output)"
        }

    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Command failed: {error}")


# Tool registry
tool_functions = {
    "set_user_name": set_user_name,
    "make_directory": make_directory,
    "read_file": read_file,
    "write_file": write_file,
    "append_file": append_file,
    "list_files": list_files,
    "run_commands": run_commands
}


# Dispatcher
def dispatch_tool(tool_name, arguments):
    function = tool_functions.get(tool_name)

    if function is None:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

    try:
        result = function(**arguments)

        return {
            "success": True,
            "result": result
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }


# Tool descriptions
tools = [
    {
        "type": "function",
        "function": {
            "name": "set_user_name",
            "description": (
                "Set the user's preferred name when they explicitly "
                "state what they want to be called."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The user's preferred name."
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "make_directory",
            "description": "Create a directory at a specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to create."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to read."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a text file. "
                "Use only when replacing the full contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": (
                "Append text to a file without deleting existing content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path, or '.' for current."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_commands",
            "description": (
                "Execute a local command after explicit user confirmation. "
                "Use only when necessary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Complete command to execute."
                    }
                },
                "required": ["command"]
            }
        }
    }
]


# Main conversation loop
while True:

    user_input = prompt(f"{user_state['name']}: ")

    if user_input.strip().lower() in ("quit", "exit"):
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    # Limit tool rounds so the model cannot loop indefinitely.
    max_tool_rounds = 10

    for round_number in range(max_tool_rounds + 1):

        try:
            response: ChatResponse = chat(
                model=model,
                messages=messages,
                tools=tools
            )

        except Exception as error:
            print(f"Ollama error: {error}")
            break

        # Save every assistant response, including tool calls.
        messages.append(response.message)

        tool_calls = response.message.tool_calls or []

        # No more tools needed: display final answer.
        if not tool_calls:
            print(f"BOT: {response.message.content}")
            break

        # Stop if too many consecutive tool rounds.
        if round_number == max_tool_rounds:
            print("BOT: Tool call limit reached.")
            break

        # Execute each tool requested by the model.
        for tool_call in tool_calls:

            name = tool_call.function.name
            arguments = tool_call.function.arguments

            print(f"\n[Tool requested: {name}]")

            result = dispatch_tool(name, arguments)

            # Save tool result in the conversation history.
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result)
            })

            print(f"[Tool result: {result}]")
