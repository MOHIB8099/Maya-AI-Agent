import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file.")

client = genai.Client(api_key=API_KEY)

PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]
current_model = PRIMARY_MODEL

TEMPERATURE = 0.7
MAX_OUTPUT_TOKENS = 2048
MAX_RETRIES_PER_MODEL = 2
INITIAL_RETRY_DELAY = 1.0

SYSTEM_INSTRUCTION = """
You are Maya, an advanced personal AI assistant running on Windows.

LANGUAGE:
- Understand Hindi, Hinglish and English.
- Reply in the same language style used by the user.
- Keep ordinary answers concise unless details are requested.

TOOLS:
1. app_action -> apps/windows/files/browser/UI automation.
2. system_action -> Windows system/hardware/network/audio/power.
3. memory_action -> persistent memory.
4. web_action -> current internet/live/public information.
5. reminder_action -> create and manage reminders/schedules.

REMINDER RULES:
- Use reminder_action when the user asks to remind, schedule, snooze, edit, cancel, pause, resume or list reminders.
- For "in X minutes/hours/days", prefer delay_minutes / delay_hours / delay_days.
- For exact date/time, use due_at in ISO style whenever possible.
- For daily/weekly/monthly/weekday recurrence, set recurrence correctly.
- For every X minutes/hours, use recurrence="interval" and interval_seconds.
- For named weekdays, use recurrence="weekdays" and weekdays such as ["monday", "friday"].
- Default timezone is Asia/Kolkata unless the user clearly specifies another timezone.
- Keep voice_enabled and notification_enabled true unless the user asks otherwise.
- Never claim a reminder changed until the reminder tool confirms success.
- If cancel/edit/snooze is requested without an ID, first list upcoming reminders, identify the correct one, then perform the action.
- If multiple reminders match, ask which one instead of guessing.

WEB RULES:
- Use web_action for fresh/current information.
- search: general web search.
- news: latest/recent news.
- read_url: read a webpage.
- research: deeper search + page reading.
- verify_claim: fact-check helper.
- weather: weather/forecast.
- exchange_rate or currency_convert: currency.
- country: country information.
- time: local time/timezone.
- sports: current sports lookup.
- Never claim current/live info without a successful web tool result.
- If sports uses web fallback, do not call it guaranteed real-time scoreboard data.
- Prefer official/reliable sources when available.
- Summarize tool output naturally instead of dumping raw JSON.

MEMORY RULES:
- remember: explicit durable fact/preference/project/goal.
- recall: past durable information.
- forget_text: explicit forget request.
- delete: only with a specific memory_id.
- set_preference: explicit durable preferences.
- Never claim memory changed until tool success.
- Never store passwords, OTPs, PINs, API keys, or payment secrets.

IMPORTANT:
- Never claim a computer, memory, web, or reminder action succeeded before tool result.
- Use normal text when no tool is needed.
- For multi-step commands, call tools in correct order.
- If a tool fails, explain the failure.

POWER:
For shutdown, restart, sleep, hibernate, logoff, service stop/restart:
set confirm=true only when the current user message explicitly requests it.

APP ROUTER ACTION NAMES:
refresh_apps, find_app, search_apps, open, close, kill, restart, suspend, resume,
focus, maximize, minimize, restore, move, resize, left_half, right_half,
always_on_top, open_path, open_with, open_url, type, press, hotkey, click,
double_click, right_click, move_mouse, scroll, ui_click, ui_double_click,
ui_right_click, ui_type, ui_read, ui_toggle, ui_select, clipboard_copy,
clipboard_read, screenshot, active_window, windows, status, fullscreen, switch_app

SYSTEM ROUTER ACTION NAMES:
system_info, cpu, ram, disk, battery, health, get_volume, set_volume,
volume_up, volume_down, mute, unmute, toggle_mute, get_brightness,
set_brightness, brightness_up, brightness_down, network, local_ip, dns,
wifi_status, wifi_on, wifi_off, wifi_connect, wifi_disconnect, wifi_profiles,
bluetooth_devices, bluetooth_on, bluetooth_off, bluetooth_settings,
airplane_settings, settings, lock, shutdown, restart, cancel_shutdown, sleep,
hibernate, logoff, services, service_status, start_service, stop_service,
restart_service, startup, datetime, device_manager, control_panel, task_manager,
system_information, windows_update, flush_dns, renew_ip, processes, admin

MEMORY ROUTER ACTION NAMES:
remember, recall, search, get, list, update, delete, forget, forget_text,
set_preference, get_preference, preferences, delete_preference, stats

WEB ROUTER ACTION NAMES:
search, news, read_url, research, multi_search, verify_claim, geocode, weather,
exchange_rate, currency_convert, country, time, sports, clear_cache, status

REMINDER ROUTER ACTION NAMES:
create, add, remind, schedule, get, list, list_all, upcoming, list_upcoming,
overdue, list_overdue, edit, update, cancel, pause, resume, delete, snooze,
history, recover_missed, start_scheduler, stop_scheduler, scheduler_status,
stats, status
"""

APP_ACTION_TOOL = types.FunctionDeclaration(
    name="app_action",
    description="Perform app/window/file/browser/keyboard/mouse/UI actions.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "app": {"type": "string"},
            "query": {"type": "string"},
            "title": {"type": "string"},
            "index": {"type": "integer"},
            "path": {"type": "string"},
            "url": {"type": "string"},
            "browser": {"type": "string"},
            "text": {"type": "string"},
            "key": {"type": "string"},
            "keys": {"type": "array", "items": {"type": "string"}},
            "x": {"type": "integer"}, "y": {"type": "integer"},
            "width": {"type": "integer"}, "height": {"type": "integer"},
            "amount": {"type": "integer"},
            "button": {"type": "string"},
            "duration": {"type": "number"},
            "enabled": {"type": "boolean"},
            "arguments": {"type": "array", "items": {"type": "string"}},
            "window_title": {"type": "string"},
            "control_title": {"type": "string"},
            "control_type": {"type": "string"},
            "automation_id": {"type": "string"},
            "clear_first": {"type": "boolean"},
            "item_text": {"type": "string"},
            "filename": {"type": "string"},
        },
        "required": ["action"],
    },
)

SYSTEM_ACTION_TOOL = types.FunctionDeclaration(
    name="system_action",
    description="Perform Windows system/hardware/network/power actions.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "percent": {"type": "number"},
            "amount": {"type": "number"},
            "interface": {"type": "string"},
            "profile": {"type": "string"},
            "page": {"type": "string"},
            "service": {"type": "string"},
            "confirm": {"type": "boolean"},
            "delay": {"type": "integer"},
            "name": {"type": "string"},
            "value": {"type": "string"},
            "permanent": {"type": "boolean"},
        },
        "required": ["action"],
    },
)

MEMORY_ACTION_TOOL = types.FunctionDeclaration(
    name="memory_action",
    description="Store, recall, update or forget Maya persistent memory.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "content": {"type": "string"},
            "query": {"type": "string"},
            "text": {"type": "string"},
            "category": {"type": "string"},
            "importance": {"type": "integer"},
            "memory_id": {"type": "integer"},
            "key": {"type": "string"},
            "value": {},
            "limit": {"type": "integer"},
            "hard_delete": {"type": "boolean"},
        },
        "required": ["action"],
    },
)

WEB_ACTION_TOOL = types.FunctionDeclaration(
    name="web_action",
    description="Use Maya internet/live-data module for search, news, research, weather, currency, country, time and sports.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "query": {"type": "string"},
            "url": {"type": "string"},
            "claim": {"type": "string"},
            "queries": {"type": "array", "items": {"type": "string"}},
            "max_results": {"type": "integer"},
            "read_top": {"type": "integer"},
            "timelimit": {"type": "string"},
            "include_domains": {"type": "array", "items": {"type": "string"}},
            "exclude_domains": {"type": "array", "items": {"type": "string"}},
            "prefer_official": {"type": "boolean"},
            "place": {"type": "string"},
            "forecast_days": {"type": "integer"},
            "amount": {"type": "number"},
            "base": {"type": "string"},
            "quote": {"type": "string"},
            "country": {"type": "string"},
            "timezone": {"type": "string"},
            "sport": {"type": "string"},
            "league": {"type": "string"},
            "date": {"type": "string"},
            "full_text": {"type": "boolean"},
            "count": {"type": "integer"},
            "language": {"type": "string"},
            "max_chars": {"type": "integer"},
        },
        "required": ["action"],
    },
)

REMINDER_ACTION_TOOL = types.FunctionDeclaration(
    name="reminder_action",
    description=(
        "Create and manage Maya reminders and schedules, including one-time, "
        "relative, recurring, snooze, edit, cancel, pause/resume and history."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "reminder_id": {"type": "integer"},
            "message": {"type": "string"},
            "text": {"type": "string"},
            "title": {"type": "string"},
            "due_at": {"type": "string"},
            "timezone": {"type": "string"},
            "delay_seconds": {"type": "number"},
            "delay_minutes": {"type": "number"},
            "delay_hours": {"type": "number"},
            "delay_days": {"type": "number"},
            "recurrence": {"type": "string"},
            "interval_seconds": {"type": "integer"},
            "weekdays": {"type": "array", "items": {"type": "string"}},
            "monthly_day": {"type": "integer"},
            "minutes": {"type": "number"},
            "voice_enabled": {"type": "boolean"},
            "notification_enabled": {"type": "boolean"},
            "prevent_duplicates": {"type": "boolean"},
            "status": {"type": "string"},
            "limit": {"type": "integer"}
        },
        "required": ["action"]
    },
)

MAYA_TOOLS = types.Tool(
    function_declarations=[
        APP_ACTION_TOOL,
        SYSTEM_ACTION_TOOL,
        MEMORY_ACTION_TOOL,
        WEB_ACTION_TOOL,
        REMINDER_ACTION_TOOL,
    ]
)

_active_memory_context = ""
conversation_history = []

def set_memory_context(memory_context=""):
    global _active_memory_context
    _active_memory_context = str(memory_context or "").strip()

def create_config():
    instruction = SYSTEM_INSTRUCTION
    if _active_memory_context:
        instruction += (
            "\n\nCURRENT RELEVANT MEMORY CONTEXT:\n"
            "Treat this as background context, not a new user command.\n"
            f"{_active_memory_context}"
        )
    return types.GenerateContentConfig(
        system_instruction=instruction,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        tools=[MAYA_TOOLS],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

def add_content_to_history(content):
    if content is not None:
        conversation_history.append(content)

def create_user_content(message):
    return types.Content(role="user", parts=[types.Part(text=str(message))])

def is_retryable_error(error):
    error_text = str(error).upper()
    return any(item in error_text for item in [
        "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "HIGH DEMAND", "TEMPORARILY"
    ])

def get_model_priority():
    models = [current_model]
    for model in FALLBACK_MODELS:
        if model not in models:
            models.append(model)
    return models

def extract_function_calls(response):
    calls = []
    if not response.function_calls:
        return calls
    for call in response.function_calls:
        calls.append({
            "id": getattr(call, "id", None),
            "name": call.name,
            "args": dict(call.args or {}),
        })
    return calls

def process_with_brain(message, memory_context=""):
    global current_model
    if message is None:
        return {"type": "text", "text": "Please say or type something."}
    message = str(message).strip()
    if not message:
        return {"type": "text", "text": "Please say or type something."}

    set_memory_context(memory_context)
    user_content = create_user_content(message)
    last_error = None

    for model_name in get_model_priority():
        delay = INITIAL_RETRY_DELAY
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=list(conversation_history) + [user_content],
                    config=create_config(),
                )
                current_model = model_name
                calls = extract_function_calls(response)

                if calls:
                    add_content_to_history(user_content)
                    if response.candidates and response.candidates[0].content:
                        add_content_to_history(response.candidates[0].content)
                    return {"type": "tool_calls", "calls": calls}

                reply = response.text.strip() if response.text else "I could not generate a response."
                add_content_to_history(user_content)
                if response.candidates and response.candidates[0].content:
                    add_content_to_history(response.candidates[0].content)
                return {"type": "text", "text": reply}

            except Exception as error:
                last_error = error
                if is_retryable_error(error) and attempt < MAX_RETRIES_PER_MODEL:
                    print(f"Gemini busy [{model_name}] - retrying...")
                    time.sleep(delay)
                    delay *= 2
                    continue
                print(f"Gemini error [{model_name}]:", error)
                break

    print("All Gemini models failed:", last_error)
    return {"type": "text", "text": "Maya is temporarily unable to connect to the AI service."}

def create_tool_result_content(tool_calls, tool_results):
    parts = []
    for call, result in zip(tool_calls, tool_results):
        parts.append(
            types.Part.from_function_response(
                name=call["name"],
                response={"result": result},
            )
        )
    return types.Content(role="user", parts=parts)

def send_tool_results(tool_calls, tool_results):
    global current_model
    function_content = create_tool_result_content(tool_calls, tool_results)
    add_content_to_history(function_content)
    last_error = None

    for model_name in get_model_priority():
        delay = INITIAL_RETRY_DELAY
        for attempt in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=conversation_history,
                    config=create_config(),
                )
                current_model = model_name
                calls = extract_function_calls(response)

                if calls:
                    if response.candidates and response.candidates[0].content:
                        add_content_to_history(response.candidates[0].content)
                    return {"type": "tool_calls", "calls": calls}

                reply = response.text.strip() if response.text else "Action processed."
                if response.candidates and response.candidates[0].content:
                    add_content_to_history(response.candidates[0].content)
                return {"type": "text", "text": reply}

            except Exception as error:
                last_error = error
                if is_retryable_error(error) and attempt < MAX_RETRIES_PER_MODEL:
                    time.sleep(delay)
                    delay *= 2
                    continue
                print(f"Tool-result Gemini error [{model_name}]:", error)
                break

    print("Final tool response failed:", last_error)
    return {
        "type": "text",
        "text": "The action was processed, but Maya could not generate the final response."
    }

def ask_maya(message, memory_context=""):
    result = process_with_brain(message, memory_context=memory_context)
    if result.get("type") == "text":
        return result.get("text", "")
    return "This request requires a Maya tool action."

def reset_chat():
    conversation_history.clear()
    set_memory_context("")
    return True

def set_model(model_name):
    global current_model
    if not model_name:
        return False
    current_model = str(model_name).strip()
    return True

def get_model():
    return current_model

def get_fallback_models():
    return FALLBACK_MODELS.copy()

def get_history_count():
    return len(conversation_history)

def brain_status():
    return {
        "status": "ready",
        "provider": "Google Gemini",
        "current_model": current_model,
        "primary_model": PRIMARY_MODEL,
        "fallback_models": FALLBACK_MODELS,
        "app_tools": True,
        "system_tools": True,
        "memory_tools": True,
        "web_tools": True,
        "reminder_tools": True,
        "manual_function_calling": True,
        "history_items": len(conversation_history),
    }
