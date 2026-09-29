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

from apps import (
    execute_app_action,
    apps_module_status,
)

from system import (
    execute_system_action,
    system_module_status,
)

from memory import (
    execute_memory_action,
    memory_module_status,
    save_conversation_message,
    auto_save_from_message,
    memory_context_as_text,
)


# =========================================================
# 1. SETTINGS
# =========================================================

MAX_TOOL_ROUNDS = 12

ACTIVE_USER_ID = "default"
ACTIVE_SESSION_ID = "default"


# =========================================================
# 2. ACTIVE USER / SESSION
# =========================================================

def set_active_user(user_id, session_id=None):
    """
    GUI future me logged-in username yahan set kar sakta hai.
    Existing GUI calls break nahi honge; default user fallback rahega.
    """
    global ACTIVE_USER_ID
    global ACTIVE_SESSION_ID

    clean_user_id = str(user_id or "").strip()

    if not clean_user_id:
        clean_user_id = "default"

    ACTIVE_USER_ID = clean_user_id

    if session_id is not None:
        clean_session_id = str(session_id or "").strip()
        ACTIVE_SESSION_ID = clean_session_id or "default"

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


# =========================================================
# 3. NORMALIZE TOOL RESULT
# =========================================================

def normalize_tool_result(result):
    if isinstance(result, dict):
        return result

    if isinstance(result, bool):
        return {
            "success": result,
        }

    if isinstance(result, list):
        return {
            "success": True,
            "items": result,
        }

    return {
        "success": True,
        "result": result,
    }


# =========================================================
# 4. EXECUTE APP ACTION
# =========================================================

def execute_app_tool(args):
    if not isinstance(args, dict):
        return {
            "success": False,
            "message": "Invalid app action arguments.",
        }

    action = args.get("action")

    if not action:
        return {
            "success": False,
            "message": "App action name is missing.",
        }

    tool_args = dict(args)
    tool_args.pop("action", None)

    try:
        result = execute_app_action(
            action,
            **tool_args,
        )
        return normalize_tool_result(result)

    except Exception as error:
        return {
            "success": False,
            "message": str(error),
        }


# =========================================================
# 5. EXECUTE SYSTEM ACTION
# =========================================================

def execute_system_tool(args):
    if not isinstance(args, dict):
        return {
            "success": False,
            "message": "Invalid system action arguments.",
        }

    action = args.get("action")

    if not action:
        return {
            "success": False,
            "message": "System action name is missing.",
        }

    tool_args = dict(args)
    tool_args.pop("action", None)

    try:
        result = execute_system_action(
            action,
            **tool_args,
        )
        return normalize_tool_result(result)

    except Exception as error:
        return {
            "success": False,
            "message": str(error),
        }


# =========================================================
# 6. EXECUTE MEMORY ACTION
# =========================================================

def execute_memory_tool(args):
    """
    Brain ke memory_action ko memory.py ke central router tak bhejta hai.
    user_id model se accept nahi kiya jata; controller current user set karta hai.
    """
    if not isinstance(args, dict):
        return {
            "success": False,
            "message": "Invalid memory action arguments.",
        }

    action = args.get("action")

    if not action:
        return {
            "success": False,
            "message": "Memory action name is missing.",
        }

    tool_args = dict(args)
    tool_args.pop("action", None)
    tool_args.pop("user_id", None)

    # Brain ke common wording ko memory.py ke expected fields se align karna.
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
        result = execute_memory_action(
            action,
            user_id=ACTIVE_USER_ID,
            **tool_args,
        )
        return normalize_tool_result(result)

    except Exception as error:
        return {
            "success": False,
            "message": str(error),
        }


# =========================================================
# 7. EXECUTE ONE MAYA TOOL CALL
# =========================================================

def execute_tool_call(call):
    if not isinstance(call, dict):
        return {
            "success": False,
            "message": "Invalid tool call.",
        }

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

    else:
        result = {
            "success": False,
            "message": f"Unknown Maya tool: {tool_name}",
        }

    print(f"Result: {result}")
    return result


# =========================================================
# 8. HANDLE BRAIN RESULT
# =========================================================

def handle_brain_result(result):
    current_result = result

    for _round_number in range(MAX_TOOL_ROUNDS):
        if not isinstance(current_result, dict):
            return "Maya received an invalid brain response."

        result_type = current_result.get("type")

        if result_type == "text":
            return current_result.get("text", "")

        if result_type == "tool_calls":
            tool_calls = current_result.get("calls", [])

            if not tool_calls:
                return "Maya received an empty tool request."

            tool_results = []

            for call in tool_calls:
                result = execute_tool_call(call)
                tool_results.append(result)

            current_result = send_tool_results(
                tool_calls,
                tool_results,
            )
            continue

        return "Maya received an unknown brain response."

    return (
        "Maya stopped the action because too many tool steps "
        "were requested."
    )


# =========================================================
# 9. MEMORY HELPERS FOR NORMAL CHAT
# =========================================================

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
        return {
            "success": False,
            "message": str(error),
        }


def _safe_auto_memory(user_input):
    try:
        return auto_save_from_message(
            text=user_input,
            user_id=ACTIVE_USER_ID,
        )
    except Exception as error:
        print("Memory auto-save error:", error)
        return {
            "success": False,
            "message": str(error),
        }


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


# =========================================================
# 10. MAIN TEXT PROCESSING
# =========================================================

def process_text(user_input):
    """
    Typed text ka full Maya flow:
    user -> memory -> brain -> tools -> final reply -> memory
    """
    if user_input is None:
        return "Please type something."

    user_input = str(user_input).strip()

    if not user_input:
        return "Please type something."

    # Current user message short-term memory me save.
    _safe_save_message(
        "user",
        user_input,
    )

    # Sirf conservative patterns durable memory me auto-save honge.
    _safe_auto_memory(user_input)

    # Current question ke relevant old memories brain ko dena.
    memory_context = _safe_memory_context(user_input)

    brain_result = process_with_brain(
        user_input,
        memory_context=memory_context,
    )

    reply = handle_brain_result(brain_result)

    # Final Maya reply short-term memory me save.
    if reply:
        _safe_save_message(
            "assistant",
            reply,
        )

    return reply


# =========================================================
# 11. SMART VOICE PROCESSING
# =========================================================

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


# =========================================================
# 12. FIXED VOICE FALLBACK
# =========================================================

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


# =========================================================
# 13. TEXT INPUT + VOICE OUTPUT
# =========================================================

def process_text_and_speak(user_input):
    reply = process_text(user_input)

    print("Maya:", reply)

    speak(reply)

    return reply


# =========================================================
# 14. ASYNC VOICE OUTPUT
# =========================================================

def process_text_and_speak_async(user_input):
    reply = process_text(user_input)

    print("Maya:", reply)

    speak_async(reply)

    return reply


# =========================================================
# 15. STOP MAYA SPEAKING
# =========================================================

def stop_maya_voice():
    stop_speaking()
    return True


# =========================================================
# 16. RESET CURRENT CHAT
# =========================================================

def reset_maya_chat():
    """
    Gemini temporary context reset hota hai.
    Long-term memory delete nahi hoti.
    """
    return reset_chat()


# =========================================================
# 17. MAYA STATUS
# =========================================================

def get_maya_status():
    status = {
        "maya": "ready",
        "active_user": ACTIVE_USER_ID,
        "active_session": ACTIVE_SESSION_ID,
    }

    try:
        status["brain"] = brain_status()
    except Exception as error:
        status["brain"] = {
            "status": "error",
            "message": str(error),
        }

    try:
        status["voice"] = voice_status()
    except Exception as error:
        status["voice"] = {
            "status": "error",
            "message": str(error),
        }

    try:
        status["apps"] = apps_module_status()
    except Exception as error:
        status["apps"] = {
            "status": "error",
            "message": str(error),
        }

    try:
        status["system"] = system_module_status()
    except Exception as error:
        status["system"] = {
            "status": "error",
            "message": str(error),
        }

    try:
        status["memory"] = memory_module_status()
    except Exception as error:
        status["memory"] = {
            "status": "error",
            "message": str(error),
        }

    return status