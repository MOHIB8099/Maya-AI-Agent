from brain import (
    process_with_brain,
    send_tool_results,
    reset_chat,
    brain_status,
)
from voice import (
    smart_listen,
    listen,
    speak,
    speak_async,
    stop_speaking,
    voice_status,
)
from apps import execute_app_action, apps_module_status
from system import execute_system_action, system_module_status
from memory import (
    execute_memory_action,
    memory_module_status,
    save_conversation_message,
    auto_save_from_message,
    memory_context_as_text,
)
from web_search import execute_web_action, web_search_status
from reminders import execute_reminder_action, reminders_module_status

MAX_TOOL_ROUNDS = 12
ACTIVE_USER_ID = "default"
ACTIVE_SESSION_ID = "default"

def set_active_user(user_id, session_id=None):
    global ACTIVE_USER_ID, ACTIVE_SESSION_ID
    ACTIVE_USER_ID = str(user_id or "").strip() or "default"
    if session_id is not None:
        ACTIVE_SESSION_ID = str(session_id or "").strip() or "default"
    return {
        "success": True,
        "user_id": ACTIVE_USER_ID,
        "session_id": ACTIVE_SESSION_ID,
    }

def get_active_user():
    return {
        "user_id": ACTIVE_USER_ID,
        "session_id": ACTIVE_SESSION_ID,
    }

def normalize_tool_result(result):
    if isinstance(result, dict):
        return result
    if isinstance(result, bool):
        return {"success": result}
    if isinstance(result, list):
        return {"success": True, "items": result}
    return {"success": True, "result": result}

def execute_app_tool(args):
    if not isinstance(args, dict):
        return {"success": False, "message": "Invalid app action arguments."}
    action = args.get("action")
    if not action:
        return {"success": False, "message": "App action name is missing."}
    tool_args = dict(args)
    tool_args.pop("action", None)
    try:
        return normalize_tool_result(execute_app_action(action, **tool_args))
    except Exception as error:
        return {"success": False, "message": str(error)}

def execute_system_tool(args):
    if not isinstance(args, dict):
        return {"success": False, "message": "Invalid system action arguments."}
    action = args.get("action")
    if not action:
        return {"success": False, "message": "System action name is missing."}
    tool_args = dict(args)
    tool_args.pop("action", None)
    try:
        return normalize_tool_result(execute_system_action(action, **tool_args))
    except Exception as error:
        return {"success": False, "message": str(error)}

def execute_memory_tool(args):
    if not isinstance(args, dict):
        return {"success": False, "message": "Invalid memory action arguments."}
    action = args.get("action")
    if not action:
        return {"success": False, "message": "Memory action name is missing."}

    tool_args = dict(args)
    tool_args.pop("action", None)
    tool_args.pop("user_id", None)

    if action in {"remember", "add", "save"}:
        if not tool_args.get("content") and tool_args.get("text"):
            tool_args["content"] = tool_args.pop("text")

    if action in {"recall", "search"}:
        if not tool_args.get("query") and tool_args.get("text"):
            tool_args["query"] = tool_args.pop("text")

    if action == "forget_text":
        if not tool_args.get("text") and tool_args.get("content"):
            tool_args["text"] = tool_args.pop("content")

    try:
        return normalize_tool_result(
            execute_memory_action(
                action,
                user_id=ACTIVE_USER_ID,
                **tool_args,
            )
        )
    except Exception as error:
        return {"success": False, "message": str(error)}

def execute_web_tool(args):
    if not isinstance(args, dict):
        return {"success": False, "message": "Invalid web action arguments."}

    action = args.get("action")
    if not action:
        return {"success": False, "message": "Web action name is missing."}

    tool_args = dict(args)
    tool_args.pop("action", None)
    tool_args.pop("user_id", None)
    tool_args.pop("session_id", None)

    if action in {"search", "news", "research"}:
        if not tool_args.get("query") and tool_args.get("text"):
            tool_args["query"] = tool_args.pop("text")

    if action in {"weather", "geocode"}:
        if not tool_args.get("place") and tool_args.get("query"):
            tool_args["place"] = tool_args.get("query")

    if action == "country":
        if not tool_args.get("country") and tool_args.get("query"):
            tool_args["country"] = tool_args.get("query")

    try:
        return normalize_tool_result(
            execute_web_action(
                action,
                **tool_args,
            )
        )
    except Exception as error:
        return {"success": False, "message": str(error)}

def execute_reminder_tool(args):
    if not isinstance(args, dict):
        return {"success": False, "message": "Invalid reminder action arguments."}

    action = args.get("action")
    if not action:
        return {"success": False, "message": "Reminder action name is missing."}

    tool_args = dict(args)
    tool_args.pop("action", None)
    tool_args.pop("user_id", None)

    if action in {"create", "add", "remind", "schedule"}:
        if not tool_args.get("message") and tool_args.get("text"):
            tool_args["message"] = tool_args.get("text")
        if not tool_args.get("timezone"):
            tool_args["timezone"] = "Asia/Kolkata"

    try:
        return normalize_tool_result(
            execute_reminder_action(
                action,
                user_id=ACTIVE_USER_ID,
                **tool_args,
            )
        )
    except Exception as error:
        return {"success": False, "message": str(error)}

def execute_tool_call(call):
    if not isinstance(call, dict):
        return {"success": False, "message": "Invalid tool call."}

    tool_name = call.get("name")
    args = call.get("args", {})

    print(f"\nTool: {tool_name}")
    print(f"Args: {args}")

    if tool_name == "app_action":
        result = execute_app_tool(args)
    elif tool_name == "system_action":
        result = execute_system_tool(args)
    elif tool_name == "memory_action":
        result = execute_memory_tool(args)
    elif tool_name == "web_action":
        result = execute_web_tool(args)
    elif tool_name == "reminder_action":
        result = execute_reminder_tool(args)
    else:
        result = {
            "success": False,
            "message": f"Unknown Maya tool: {tool_name}",
        }

    print(f"Result: {result}")
    return result

def handle_brain_result(result):
    current_result = result

    for _ in range(MAX_TOOL_ROUNDS):
        if not isinstance(current_result, dict):
            return "Maya received an invalid brain response."

        result_type = current_result.get("type")

        if result_type == "text":
            return current_result.get("text", "")

        if result_type == "tool_calls":
            tool_calls = current_result.get("calls", [])
            if not tool_calls:
                return "Maya received an empty tool request."

            tool_results = [execute_tool_call(call) for call in tool_calls]
            current_result = send_tool_results(tool_calls, tool_results)
            continue

        return "Maya received an unknown brain response."

    return "Maya stopped the action because too many tool steps were requested."

def _safe_save_message(role, content):
    try:
        return save_conversation_message(
            role=role,
            content=content,
            user_id=ACTIVE_USER_ID,
            session_id=ACTIVE_SESSION_ID,
        )
    except Exception as error:
        print("Memory conversation save error:", error)
        return {"success": False, "message": str(error)}

def _safe_auto_memory(user_input):
    try:
        return auto_save_from_message(
            text=user_input,
            user_id=ACTIVE_USER_ID,
        )
    except Exception as error:
        print("Memory auto-save error:", error)
        return {"success": False, "message": str(error)}

def _safe_memory_context(user_input):
    try:
        return memory_context_as_text(
            query=user_input,
            user_id=ACTIVE_USER_ID,
            session_id=ACTIVE_SESSION_ID,
            long_term_limit=8,
            short_term_limit=12,
        )
    except Exception as error:
        print("Memory context error:", error)
        return ""

def process_text(user_input):
    if user_input is None:
        return "Please type something."

    user_input = str(user_input).strip()
    if not user_input:
        return "Please type something."

    _safe_save_message("user", user_input)
    _safe_auto_memory(user_input)
    memory_context = _safe_memory_context(user_input)

    brain_result = process_with_brain(
        user_input,
        memory_context=memory_context,
    )

    reply = handle_brain_result(brain_result)

    if reply:
        _safe_save_message("assistant", reply)

    return reply

def process_voice():
    user_text = smart_listen()
    if not user_text:
        return {
            "user_text": "",
            "reply": "",
            "success": False,
        }

    print("\nYou:", user_text)
    reply = process_text(user_text)
    print("Maya:", reply)
    speak(reply)

    return {
        "user_text": user_text,
        "reply": reply,
        "success": True,
    }

def process_fixed_voice(seconds=6):
    user_text = listen(seconds)
    if not user_text:
        return {
            "user_text": "",
            "reply": "",
            "success": False,
        }

    print("\nYou:", user_text)
    reply = process_text(user_text)
    print("Maya:", reply)
    speak(reply)

    return {
        "user_text": user_text,
        "reply": reply,
        "success": True,
    }

def process_text_and_speak(user_input):
    reply = process_text(user_input)
    print("Maya:", reply)
    speak(reply)
    return reply

def process_text_and_speak_async(user_input):
    reply = process_text(user_input)
    print("Maya:", reply)
    speak_async(reply)
    return reply

def stop_maya_voice():
    stop_speaking()
    return True

def reset_maya_chat():
    return reset_chat()

def get_maya_status():
    status = {
        "maya": "ready",
        "active_user": ACTIVE_USER_ID,
        "active_session": ACTIVE_SESSION_ID,
    }

    modules = [
        ("brain", brain_status),
        ("voice", voice_status),
        ("apps", apps_module_status),
        ("system", system_module_status),
        ("memory", memory_module_status),
        ("web", web_search_status),
        ("reminders", reminders_module_status),
    ]

    for name, func in modules:
        try:
            status[name] = func()
        except Exception as error:
            status[name] = {
                "status": "error",
                "message": str(error),
            }

    return status
