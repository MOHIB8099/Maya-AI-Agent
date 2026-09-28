import os
import re
import json
import time
import shutil
import subprocess
import threading
from pathlib import Path
from difflib import SequenceMatcher

import psutil
import pyautogui
import pygetwindow as gw

import win32api
import win32con
import win32gui
import win32process
import win32clipboard
import winreg

from pywinauto import Application, Desktop
from pywinauto.findwindows import ElementNotFoundError

try:
    import win32com.client
except Exception:
    win32com = None


# =========================================================
# 1. SETTINGS
# =========================================================

DEFAULT_TIMEOUT = 10
UIA_BACKEND = "uia"

APP_CACHE_FILE = "maya_app_cache.json"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15


# =========================================================
# 2. APP ALIASES
# =========================================================

APP_ALIASES = {
    "notepad": ["notepad", "notepad.exe"],
    "calculator": ["calculator", "calc", "calc.exe"],
    "paint": ["paint", "mspaint", "mspaint.exe"],

    "cmd": [
        "cmd",
        "command prompt",
        "cmd.exe"
    ],

    "powershell": [
        "powershell",
        "windows powershell",
        "powershell.exe"
    ],

    "explorer": [
        "explorer",
        "file explorer",
        "windows explorer",
        "explorer.exe"
    ],

    "task manager": [
        "task manager",
        "taskmgr",
        "taskmgr.exe"
    ],

    "control panel": [
        "control panel",
        "control",
        "control.exe"
    ],

    "chrome": [
        "chrome",
        "google chrome"
    ],

    "edge": [
        "edge",
        "microsoft edge"
    ],

    "firefox": [
        "firefox",
        "mozilla firefox"
    ],

    "vscode": [
        "vscode",
        "vs code",
        "visual studio code",
        "code"
    ],

    "spotify": [
        "spotify"
    ],

    "discord": [
        "discord"
    ],

    "whatsapp": [
        "whatsapp"
    ]
}


# =========================================================
# 3. BUILT-IN WINDOWS COMMANDS
# =========================================================

BUILTIN_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe"
}


# =========================================================
# 4. GLOBAL APP CACHE
# =========================================================

app_cache = []


# =========================================================
# 5. BASIC HELPERS
# =========================================================

def normalize_text(text):
    if not text:
        return ""

    text = str(text).strip().lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def normalize_exe_name(name):
    name = normalize_text(name)

    if name.endswith(".exe"):
        name = name[:-4]

    return name


def safe_path(path):
    if not path:
        return None

    path = os.path.expandvars(
        os.path.expanduser(
            str(path)
        )
    )

    path = path.strip(
        '"'
    )

    return path


# =========================================================
# 6. ALIAS LOOKUP
# =========================================================

def resolve_alias(name):
    target = normalize_text(
        name
    )

    for canonical, aliases in APP_ALIASES.items():

        normalized_aliases = [
            normalize_text(alias)
            for alias in aliases
        ]

        if (
            target == canonical
            or target in normalized_aliases
        ):
            return canonical

    return target


# =========================================================
# 7. START MENU LOCATIONS
# =========================================================

def get_start_menu_paths():
    paths = []

    candidates = [
        os.path.expandvars(
            r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
        ),

        os.path.expandvars(
            r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"
        )
    ]

    for path in candidates:

        if os.path.isdir(path):
            paths.append(path)

    return paths


# =========================================================
# 8. RESOLVE WINDOWS SHORTCUT
# =========================================================

def resolve_shortcut(shortcut_path):
    """
    Resolve .lnk shortcut to executable.
    """

    try:
        shell = win32com.client.Dispatch(
            "WScript.Shell"
        )

        shortcut = shell.CreateShortcut(
            shortcut_path
        )

        target = shortcut.TargetPath
        arguments = shortcut.Arguments

        return {
            "target": target,
            "arguments": arguments
        }

    except Exception:
        return {
            "target": None,
            "arguments": ""
        }


# =========================================================
# 9. SCAN START MENU APPS
# =========================================================

def scan_start_menu_apps():
    results = []

    for base_path in get_start_menu_paths():

        for root, folders, files in os.walk(
            base_path
        ):

            for filename in files:

                if not filename.lower().endswith(
                    ".lnk"
                ):
                    continue

                full_path = os.path.join(
                    root,
                    filename
                )

                app_name = os.path.splitext(
                    filename
                )[0]

                shortcut = resolve_shortcut(
                    full_path
                )

                target = shortcut.get(
                    "target"
                )

                results.append(
                    {
                        "name": app_name,
                        "normalized_name":
                            normalize_text(app_name),

                        "kind": "shortcut",

                        "path": target,

                        "shortcut":
                            full_path,

                        "arguments":
                            shortcut.get(
                                "arguments",
                                ""
                            ),

                        "app_id": None,

                        "source":
                            "start_menu"
                    }
                )

    return results


# =========================================================
# 10. WINDOWS APP PATHS REGISTRY
# =========================================================

def scan_app_paths_registry():
    results = []

    registry_locations = [
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        ),

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        ),

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"
        )
    ]

    for root, registry_path in registry_locations:

        try:
            base_key = winreg.OpenKey(
                root,
                registry_path
            )

        except Exception:
            continue

        index = 0

        while True:

            try:
                subkey_name = winreg.EnumKey(
                    base_key,
                    index
                )

                index += 1

            except OSError:
                break

            try:

                subkey = winreg.OpenKey(
                    base_key,
                    subkey_name
                )

                target, _ = winreg.QueryValueEx(
                    subkey,
                    None
                )

                target = safe_path(
                    target
                )

                name = os.path.splitext(
                    subkey_name
                )[0]

                results.append(
                    {
                        "name": name,
                        "normalized_name":
                            normalize_text(name),

                        "kind": "exe",

                        "path": target,

                        "shortcut": None,
                        "arguments": "",
                        "app_id": None,

                        "source":
                            "registry_app_paths"
                    }
                )

            except Exception:
                continue

    return results


# =========================================================
# 11. UNINSTALL REGISTRY APPS
# =========================================================

def scan_installed_programs_registry():
    results = []

    registry_locations = [
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        ),

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        ),

        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        )
    ]

    for root, registry_path in registry_locations:

        try:
            base_key = winreg.OpenKey(
                root,
                registry_path
            )

        except Exception:
            continue

        index = 0

        while True:

            try:
                subkey_name = winreg.EnumKey(
                    base_key,
                    index
                )

                index += 1

            except OSError:
                break

            try:
                subkey = winreg.OpenKey(
                    base_key,
                    subkey_name
                )

                try:
                    display_name, _ = (
                        winreg.QueryValueEx(
                            subkey,
                            "DisplayName"
                        )
                    )

                except Exception:
                    continue

                install_location = ""

                try:
                    install_location, _ = (
                        winreg.QueryValueEx(
                            subkey,
                            "InstallLocation"
                        )
                    )

                except Exception:
                    pass

                display_icon = ""

                try:
                    display_icon, _ = (
                        winreg.QueryValueEx(
                            subkey,
                            "DisplayIcon"
                        )
                    )

                except Exception:
                    pass

                executable = None

                if display_icon:

                    executable = (
                        display_icon
                        .split(",")[0]
                        .strip('"')
                    )

                    if not os.path.exists(
                        executable
                    ):
                        executable = None

                results.append(
                    {
                        "name":
                            display_name,

                        "normalized_name":
                            normalize_text(
                                display_name
                            ),

                        "kind":
                            "installed_program",

                        "path":
                            executable,

                        "install_location":
                            install_location,

                        "shortcut":
                            None,

                        "arguments":
                            "",

                        "app_id":
                            None,

                        "source":
                            "uninstall_registry"
                    }
                )

            except Exception:
                continue

    return results


# =========================================================
# 12. MICROSOFT STORE / UWP APPS
# =========================================================

def scan_uwp_apps():
    """
    Uses Get-StartApps to discover Store/UWP apps.
    """

    command = (
        "Get-StartApps | "
        "Select-Object Name,AppID | "
        "ConvertTo-Json -Compress"
    )

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                command
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return []

        text = result.stdout.strip()

        if not text:
            return []

        data = json.loads(
            text
        )

        if isinstance(data, dict):
            data = [data]

        results = []

        for item in data:

            name = item.get(
                "Name"
            )

            app_id = item.get(
                "AppID"
            )

            if not name or not app_id:
                continue

            results.append(
                {
                    "name": name,

                    "normalized_name":
                        normalize_text(name),

                    "kind":
                        "uwp",

                    "path":
                        None,

                    "shortcut":
                        None,

                    "arguments":
                        "",

                    "app_id":
                        app_id,

                    "source":
                        "get_start_apps"
                }
            )

        return results

    except Exception:
        return []


# =========================================================
# 13. DEDUPLICATE APP LIST
# =========================================================

def deduplicate_apps(apps):
    seen = set()
    result = []

    for app in apps:

        key = (
            normalize_text(
                app.get("name")
            ),

            app.get("path"),

            app.get("app_id")
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            app
        )

    return result


# =========================================================
# 14. BUILD APP CACHE
# =========================================================

def build_app_cache():
    global app_cache

    discovered = []

    discovered.extend(
        scan_start_menu_apps()
    )

    discovered.extend(
        scan_app_paths_registry()
    )

    discovered.extend(
        scan_installed_programs_registry()
    )

    discovered.extend(
        scan_uwp_apps()
    )

    # Built-in apps
    for name, executable in BUILTIN_APPS.items():

        discovered.append(
            {
                "name": name,
                "normalized_name":
                    normalize_text(name),

                "kind": "builtin",

                "path":
                    executable,

                "shortcut":
                    None,

                "arguments":
                    "",

                "app_id":
                    None,

                "source":
                    "builtin"
            }
        )

    app_cache = deduplicate_apps(
        discovered
    )

    try:

        with open(
            APP_CACHE_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                app_cache,
                file,
                indent=2,
                ensure_ascii=False
            )

    except Exception:
        pass

    return app_cache


# =========================================================
# 15. LOAD APP CACHE
# =========================================================

def load_app_cache():
    global app_cache

    if app_cache:
        return app_cache

    if os.path.exists(
        APP_CACHE_FILE
    ):

        try:

            with open(
                APP_CACHE_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                app_cache = json.load(
                    file
                )

                return app_cache

        except Exception:
            pass

    return build_app_cache()


# =========================================================
# 16. REFRESH APP CACHE
# =========================================================

def refresh_app_cache():
    return build_app_cache()


# =========================================================
# 17. FUZZY APP SCORE
# =========================================================

def app_match_score(
    search_name,
    app_name
):
    search_name = normalize_text(
        search_name
    )

    app_name = normalize_text(
        app_name
    )

    if search_name == app_name:
        return 1.0

    if search_name in app_name:
        return 0.95

    if app_name in search_name:
        return 0.9

    return SequenceMatcher(
        None,
        search_name,
        app_name
    ).ratio()


# =========================================================
# 18. FIND INSTALLED APP
# =========================================================

def find_installed_app(
    app_name,
    minimum_score=0.55
):
    if not app_name:
        return None

    target = resolve_alias(
        app_name
    )

    apps = load_app_cache()

    best_match = None
    best_score = 0.0

    for app in apps:

        score = app_match_score(
            target,
            app.get(
                "normalized_name",
                app.get("name", "")
            )
        )

        if score > best_score:

            best_score = score
            best_match = app

    if best_score < minimum_score:
        return None

    result = dict(
        best_match
    )

    result["match_score"] = (
        best_score
    )

    return result


# =========================================================
# 19. SEARCH APPS
# =========================================================

def search_apps(
    query,
    limit=10
):
    apps = load_app_cache()

    matches = []

    for app in apps:

        score = app_match_score(
            query,
            app.get(
                "name",
                ""
            )
        )

        if score >= 0.4:

            item = dict(
                app
            )

            item["match_score"] = score

            matches.append(
                item
            )

    matches.sort(
        key=lambda x:
            x["match_score"],
        reverse=True
    )

    return matches[:limit]


# =========================================================
# 20. OPEN UWP APP
# =========================================================

def open_uwp_app(app_id):
    try:

        subprocess.Popen(
            [
                "explorer.exe",
                f"shell:AppsFolder\\{app_id}"
            ]
        )

        return True

    except Exception:
        return False


# =========================================================
# 21. OPEN APPLICATION
# =========================================================

def open_app(
    app_name,
    arguments=None,
    wait_for_open=True
):
    app = find_installed_app(
        app_name
    )

    if not app:

        # Try PATH directly
        direct = shutil.which(
            app_name
        )

        if not direct:

            direct = shutil.which(
                f"{app_name}.exe"
            )

        if direct:

            app = {
                "name": app_name,
                "kind": "exe",
                "path": direct,
                "arguments": "",
                "app_id": None
            }

        else:

            return {
                "success": False,
                "message":
                    f"App not found: {app_name}"
            }

    try:

        kind = app.get(
            "kind"
        )

        # ---------------------------------------------
        # UWP
        # ---------------------------------------------

        if kind == "uwp":

            success = open_uwp_app(
                app.get("app_id")
            )

            if not success:

                return {
                    "success": False,
                    "message":
                        f"Could not open {app_name}"
                }

        # ---------------------------------------------
        # Shortcut
        # ---------------------------------------------

        elif app.get(
            "shortcut"
        ):

            os.startfile(
                app["shortcut"]
            )

        # ---------------------------------------------
        # Executable
        # ---------------------------------------------

        elif app.get(
            "path"
        ):

            command = [
                app["path"]
            ]

            stored_args = app.get(
                "arguments"
            )

            if stored_args:
                command.append(
                    stored_args
                )

            if arguments:

                if isinstance(
                    arguments,
                    list
                ):
                    command.extend(
                        arguments
                    )

                else:
                    command.append(
                        str(arguments)
                    )

            subprocess.Popen(
                command
            )

        else:

            return {
                "success": False,
                "message":
                    f"No launch method for {app_name}"
            }

        if wait_for_open:

            opened = wait_for_app_open(
                app_name,
                timeout=DEFAULT_TIMEOUT
            )

        else:
            opened = True

        return {
            "success": True,
            "message":
                f"Opened {app.get('name', app_name)}",

            "verified":
                opened,

            "app":
                app
        }

    except Exception as error:

        return {
            "success": False,
            "message":
                str(error)
        }


# =========================================================
# 22. PROCESS SEARCH
# =========================================================

def find_processes(
    app_name
):
    target = normalize_exe_name(
        app_name
    )

    results = []

    for process in psutil.process_iter(
        [
            "pid",
            "name",
            "exe",
            "status",
            "memory_info"
        ]
    ):

        try:

            name = (
                process.info["name"]
                or ""
            )

            simple_name = normalize_exe_name(
                name
            )

            exe = (
                process.info["exe"]
                or ""
            )

            if (
                target in simple_name
                or simple_name in target
                or target in normalize_text(exe)
            ):

                memory_mb = None

                memory_info = (
                    process.info.get(
                        "memory_info"
                    )
                )

                if memory_info:

                    memory_mb = round(
                        memory_info.rss
                        / 1024
                        / 1024,
                        2
                    )

                results.append(
                    {
                        "pid":
                            process.info[
                                "pid"
                            ],

                        "name":
                            name,

                        "exe":
                            exe,

                        "status":
                            process.info.get(
                                "status"
                            ),

                        "memory_mb":
                            memory_mb
                    }
                )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied
        ):
            continue

    return results


# =========================================================
# 23. ALL RUNNING PROCESSES
# =========================================================

def get_running_processes():
    results = []

    for process in psutil.process_iter(
        [
            "pid",
            "name",
            "cpu_percent",
            "memory_info"
        ]
    ):

        try:

            memory_mb = None

            if process.info[
                "memory_info"
            ]:

                memory_mb = round(
                    process.info[
                        "memory_info"
                    ].rss
                    / 1024
                    / 1024,
                    2
                )

            results.append(
                {
                    "pid":
                        process.info["pid"],

                    "name":
                        process.info["name"],

                    "cpu_percent":
                        process.info[
                            "cpu_percent"
                        ],

                    "memory_mb":
                        memory_mb
                }
            )

        except Exception:
            continue

    return results


# =========================================================
# 24. APP RUNNING STATUS
# =========================================================

def is_app_running(
    app_name
):
    return bool(
        find_processes(
            app_name
        )
    )


# =========================================================
# 25. WAIT FOR APP OPEN
# =========================================================

def wait_for_app_open(
    app_name,
    timeout=10
):
    start = time.time()

    while (
        time.time() - start
        < timeout
    ):

        if (
            is_app_running(app_name)
            or find_windows(app_name)
        ):
            return True

        time.sleep(
            0.25
        )

    return False


# =========================================================
# 26. WAIT FOR APP CLOSE
# =========================================================

def wait_for_app_close(
    app_name,
    timeout=10
):
    start = time.time()

    while (
        time.time() - start
        < timeout
    ):

        if not is_app_running(
            app_name
        ):
            return True

        time.sleep(
            0.25
        )

    return False


# =========================================================
# 27. WINDOWS ENUMERATION
# =========================================================

def get_all_windows():
    results = []

    def callback(
        hwnd,
        extra
    ):

        try:

            if not win32gui.IsWindowVisible(
                hwnd
            ):
                return

            title = win32gui.GetWindowText(
                hwnd
            )

            if not title:
                return

            _, pid = (
                win32process
                .GetWindowThreadProcessId(
                    hwnd
                )
            )

            rect = win32gui.GetWindowRect(
                hwnd
            )

            results.append(
                {
                    "hwnd":
                        hwnd,

                    "pid":
                        pid,

                    "title":
                        title,

                    "rect":
                        rect
                }
            )

        except Exception:
            pass

    win32gui.EnumWindows(
        callback,
        None
    )

    return results


# =========================================================
# 28. FIND WINDOWS
# =========================================================

def find_windows(
    title
):
    if not title:
        return []

    target = normalize_text(
        title
    )

    matches = []

    for window in get_all_windows():

        window_title = normalize_text(
            window["title"]
        )

        score = app_match_score(
            target,
            window_title
        )

        if (
            target in window_title
            or score >= 0.55
        ):

            item = dict(
                window
            )

            item["match_score"] = score

            matches.append(
                item
            )

    matches.sort(
        key=lambda x:
            x["match_score"],
        reverse=True
    )

    return matches


# =========================================================
# 29. ACTIVE WINDOW
# =========================================================

def get_active_window():
    try:

        hwnd = (
            win32gui
            .GetForegroundWindow()
        )

        if not hwnd:
            return None

        title = win32gui.GetWindowText(
            hwnd
        )

        _, pid = (
            win32process
            .GetWindowThreadProcessId(
                hwnd
            )
        )

        return {
            "hwnd": hwnd,
            "pid": pid,
            "title": title
        }

    except Exception:
        return None


# =========================================================
# 30. ACTIVATE WINDOW
# =========================================================

def activate_hwnd(
    hwnd
):
    try:

        if win32gui.IsIconic(
            hwnd
        ):

            win32gui.ShowWindow(
                hwnd,
                win32con.SW_RESTORE
            )

        win32gui.SetForegroundWindow(
            hwnd
        )

        return True

    except Exception:

        try:

            win32gui.ShowWindow(
                hwnd,
                win32con.SW_RESTORE
            )

            return True

        except Exception:
            return False


# =========================================================
# 31. FOCUS WINDOW
# =========================================================

def focus_window(
    title,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    index = max(
        0,
        min(
            int(index),
            len(windows) - 1
        )
    )

    return activate_hwnd(
        windows[index]["hwnd"]
    )


# =========================================================
# 32. MAXIMIZE WINDOW
# =========================================================

def maximize_window(
    title,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    hwnd = windows[index]["hwnd"]

    try:

        win32gui.ShowWindow(
            hwnd,
            win32con.SW_MAXIMIZE
        )

        return True

    except Exception:
        return False


# =========================================================
# 33. MINIMIZE WINDOW
# =========================================================

def minimize_window(
    title,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    try:

        win32gui.ShowWindow(
            windows[index]["hwnd"],
            win32con.SW_MINIMIZE
        )

        return True

    except Exception:
        return False


# =========================================================
# 34. RESTORE WINDOW
# =========================================================

def restore_window(
    title,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    try:

        win32gui.ShowWindow(
            windows[index]["hwnd"],
            win32con.SW_RESTORE
        )

        return True

    except Exception:
        return False


# =========================================================
# 35. MOVE / RESIZE WINDOW
# =========================================================

def move_resize_window(
    title,
    x,
    y,
    width,
    height,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    hwnd = windows[index][
        "hwnd"
    ]

    try:

        win32gui.MoveWindow(
            hwnd,
            int(x),
            int(y),
            int(width),
            int(height),
            True
        )

        return True

    except Exception:
        return False


# =========================================================
# 36. MOVE WINDOW
# =========================================================

def move_window(
    title,
    x,
    y,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    hwnd = windows[index]["hwnd"]

    left, top, right, bottom = (
        win32gui.GetWindowRect(
            hwnd
        )
    )

    width = right - left
    height = bottom - top

    return move_resize_window(
        title,
        x,
        y,
        width,
        height,
        index
    )


# =========================================================
# 37. RESIZE WINDOW
# =========================================================

def resize_window(
    title,
    width,
    height,
    index=0
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    hwnd = windows[index]["hwnd"]

    left, top, right, bottom = (
        win32gui.GetWindowRect(
            hwnd
        )
    )

    return move_resize_window(
        title,
        left,
        top,
        width,
        height,
        index
    )


# =========================================================
# 38. LEFT / RIGHT HALF
# =========================================================

def move_window_left(
    title
):
    try:

        width, height = pyautogui.size()

        return move_resize_window(
            title,
            0,
            0,
            width // 2,
            height
        )

    except Exception:
        return False


def move_window_right(
    title
):
    try:

        width, height = pyautogui.size()

        return move_resize_window(
            title,
            width // 2,
            0,
            width // 2,
            height
        )

    except Exception:
        return False


# =========================================================
# 39. ALWAYS ON TOP
# =========================================================

def set_always_on_top(
    title,
    enabled=True
):
    windows = find_windows(
        title
    )

    if not windows:
        return False

    hwnd = windows[0]["hwnd"]

    try:

        insert_after = (
            win32con.HWND_TOPMOST
            if enabled
            else win32con.HWND_NOTOPMOST
        )

        win32gui.SetWindowPos(
            hwnd,
            insert_after,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE
            | win32con.SWP_NOSIZE
        )

        return True

    except Exception:
        return False


# =========================================================
# 40. GRACEFUL WINDOW CLOSE
# =========================================================

def close_windows_gracefully(
    app_name
):
    windows = find_windows(
        app_name
    )

    closed = 0

    for window in windows:

        try:

            win32gui.PostMessage(
                window["hwnd"],
                win32con.WM_CLOSE,
                0,
                0
            )

            closed += 1

        except Exception:
            continue

    return closed


# =========================================================
# 41. CLOSE APP
# =========================================================

def close_app(
    app_name,
    force_if_needed=True
):
    graceful_count = (
        close_windows_gracefully(
            app_name
        )
    )

    if graceful_count:

        if wait_for_app_close(
            app_name,
            timeout=5
        ):

            return {
                "success": True,
                "message":
                    f"Closed {app_name}",
                "method":
                    "window_close"
            }

    processes = find_processes(
        app_name
    )

    terminated = []

    for item in processes:

        try:

            process = psutil.Process(
                item["pid"]
            )

            process.terminate()

            terminated.append(
                item["pid"]
            )

        except Exception:
            continue

    if terminated:

        if wait_for_app_close(
            app_name,
            timeout=5
        ):

            return {
                "success": True,
                "message":
                    f"Closed {app_name}",
                "method":
                    "terminate",
                "pids":
                    terminated
            }

    if force_if_needed:

        return kill_app(
            app_name
        )

    return {
        "success": False,
        "message":
            f"Could not close {app_name}"
    }


# =========================================================
# 42. FORCE KILL APP
# =========================================================

def kill_app(
    app_name
):
    processes = find_processes(
        app_name
    )

    killed = []

    for item in processes:

        try:

            process = psutil.Process(
                item["pid"]
            )

            process.kill()

            killed.append(
                item["pid"]
            )

        except Exception:
            continue

    return {
        "success":
            bool(killed),

        "message":
            (
                f"Force stopped {app_name}"
                if killed
                else f"{app_name} not found"
            ),

        "pids":
            killed
    }


# =========================================================
# 43. RESTART APP
# =========================================================

def restart_app(
    app_name
):
    app_info = find_installed_app(
        app_name
    )

    close_app(
        app_name
    )

    time.sleep(
        1
    )

    return open_app(
        app_name
    )


# =========================================================
# 44. SUSPEND PROCESS
# =========================================================

def suspend_app(
    app_name
):
    results = []

    for item in find_processes(
        app_name
    ):

        try:

            psutil.Process(
                item["pid"]
            ).suspend()

            results.append(
                item["pid"]
            )

        except Exception:
            pass

    return {
        "success": bool(results),
        "pids": results
    }


# =========================================================
# 45. RESUME PROCESS
# =========================================================

def resume_app(
    app_name
):
    results = []

    for item in find_processes(
        app_name
    ):

        try:

            psutil.Process(
                item["pid"]
            ).resume()

            results.append(
                item["pid"]
            )

        except Exception:
            pass

    return {
        "success": bool(results),
        "pids": results
    }


# =========================================================
# 46. OPEN FILE OR FOLDER
# =========================================================

def open_path(
    path
):
    path = safe_path(
        path
    )

    if not path:
        return {
            "success": False,
            "message":
                "No path provided."
        }

    if not os.path.exists(
        path
    ):
        return {
            "success": False,
            "message":
                f"Path not found: {path}"
        }

    try:

        os.startfile(
            path
        )

        return {
            "success": True,
            "message":
                f"Opened {path}"
        }

    except Exception as error:

        return {
            "success": False,
            "message":
                str(error)
        }


# =========================================================
# 47. OPEN FILE WITH SPECIFIC APP
# =========================================================

def open_with_app(
    file_path,
    app_name
):
    file_path = safe_path(
        file_path
    )

    if not os.path.exists(
        file_path
    ):

        return {
            "success": False,
            "message":
                "File not found."
        }

    app = find_installed_app(
        app_name
    )

    if not app:

        return {
            "success": False,
            "message":
                f"App not found: {app_name}"
        }

    executable = app.get(
        "path"
    )

    if not executable:

        return {
            "success": False,
            "message":
                "App does not expose a normal executable."
        }

    try:

        subprocess.Popen(
            [
                executable,
                file_path
            ]
        )

        return {
            "success": True,
            "message":
                f"Opened file with {app_name}"
        }

    except Exception as error:

        return {
            "success": False,
            "message":
                str(error)
        }


# =========================================================
# 48. OPEN URL
# =========================================================

def open_url(
    url,
    browser=None
):
    if not url:
        return False

    url = str(
        url
    ).strip()

    if not (
        url.startswith("http://")
        or url.startswith("https://")
    ):

        url = "https://" + url

    try:

        if browser:

            app = find_installed_app(
                browser
            )

            if app and app.get(
                "path"
            ):

                subprocess.Popen(
                    [
                        app["path"],
                        url
                    ]
                )

                return True

        os.startfile(
            url
        )

        return True

    except Exception:
        return False


# =========================================================
# 49. UIA CONNECT
# =========================================================

def connect_to_app(
    title=None,
    process_id=None
):
    try:

        app = Application(
            backend=UIA_BACKEND
        )

        if process_id:

            app.connect(
                process=int(
                    process_id
                ),
                timeout=DEFAULT_TIMEOUT
            )

        elif title:

            app.connect(
                title_re=
                    f".*{re.escape(str(title))}.*",
                timeout=DEFAULT_TIMEOUT
            )

        else:
            return None

        return app

    except Exception:
        return None


# =========================================================
# 50. GET UI CONTROLS
# =========================================================

def get_ui_controls(
    window_title
):
    try:

        app = connect_to_app(
            title=window_title
        )

        if not app:
            return []

        window = app.top_window()

        controls = []

        for control in window.descendants():

            try:

                info = (
                    control.element_info
                )

                controls.append(
                    {
                        "name":
                            info.name,

                        "control_type":
                            info.control_type,

                        "automation_id":
                            info.automation_id,

                        "class_name":
                            info.class_name
                    }
                )

            except Exception:
                continue

        return controls

    except Exception:
        return []


# =========================================================
# 51. FIND UI CONTROL
# =========================================================

def find_ui_control(
    window_title,
    control_title=None,
    control_type=None,
    automation_id=None
):
    try:

        app = connect_to_app(
            title=window_title
        )

        if not app:
            return None

        window = app.top_window()

        criteria = {}

        if control_title:
            criteria["title"] = (
                control_title
            )

        if control_type:
            criteria["control_type"] = (
                control_type
            )

        if automation_id:
            criteria["auto_id"] = (
                automation_id
            )

        control = (
            window.child_window(
                **criteria
            )
        )

        control.wait(
            "exists visible enabled ready",
            timeout=DEFAULT_TIMEOUT
        )

        return control

    except Exception:
        return None


# =========================================================
# 52. UI CLICK
# =========================================================

def ui_click(
    window_title,
    control_title=None,
    control_type=None,
    automation_id=None
):
    control = find_ui_control(
        window_title,
        control_title,
        control_type,
        automation_id
    )

    if not control:
        return False

    try:

        control.click_input()

        return True

    except Exception:
        return False


# =========================================================
# 53. UI DOUBLE CLICK
# =========================================================

def ui_double_click(
    window_title,
    control_title=None,
    control_type=None,
    automation_id=None
):
    control = find_ui_control(
        window_title,
        control_title,
        control_type,
        automation_id
    )

    if not control:
        return False

    try:

        control.double_click_input()

        return True

    except Exception:
        return False


# =========================================================
# 54. UI RIGHT CLICK
# =========================================================

def ui_right_click(
    window_title,
    control_title=None,
    control_type=None,
    automation_id=None
):
    control = find_ui_control(
        window_title,
        control_title,
        control_type,
        automation_id
    )

    if not control:
        return False

    try:

        control.right_click_input()

        return True

    except Exception:
        return False


# =========================================================
# 55. UI TYPE TEXT
# =========================================================

def ui_type(
    window_title,
    text,
    control_title=None,
    control_type="Edit",
    automation_id=None,
    clear_first=False
):
    control = find_ui_control(
        window_title,
        control_title,
        control_type,
        automation_id
    )

    if not control:
        return False

    try:

        control.click_input()

        if clear_first:

            pyautogui.hotkey(
                "ctrl",
                "a"
            )

        control.type_keys(
            str(text),
            with_spaces=True,
            set_foreground=True
        )

        return True

    except Exception:
        return False


# =========================================================
# 56. UI READ TEXT
# =========================================================

def ui_read_text(
    window_title,
    control_title=None,
    control_type=None,
    automation_id=None
):
    control = find_ui_control(
        window_title,
        control_title,
        control_type,
        automation_id
    )

    if not control:
        return None

    try:

        texts = (
            control.texts()
        )

        if texts:
            return " ".join(
                str(x)
                for x in texts
                if x
            )

    except Exception:
        pass

    try:

        return control.window_text()

    except Exception:
        return None


# =========================================================
# 57. UI TOGGLE
# =========================================================

def ui_toggle(
    window_title,
    control_title=None,
    automation_id=None
):
    control = find_ui_control(
        window_title,
        control_title,
        None,
        automation_id
    )

    if not control:
        return False

    try:

        if hasattr(
            control,
            "toggle"
        ):

            control.toggle()

        else:

            control.click_input()

        return True

    except Exception:
        return False


# =========================================================
# 58. UI SELECT ITEM
# =========================================================

def ui_select(
    window_title,
    item_text
):
    try:

        app = connect_to_app(
            title=window_title
        )

        if not app:
            return False

        window = app.top_window()

        item = (
            window.child_window(
                title=item_text
            )
        )

        item.wait(
            "visible enabled ready",
            timeout=DEFAULT_TIMEOUT
        )

        try:
            item.select()

        except Exception:
            item.click_input()

        return True

    except Exception:
        return False


# =========================================================
# 59. NORMAL TEXT TYPING
# =========================================================

def type_text(
    text,
    interval=0.02
):
    try:

        pyautogui.write(
            str(text),
            interval=float(
                interval
            )
        )

        return True

    except Exception:
        return False


# =========================================================
# 60. PRESS KEY
# =========================================================

def press_key(
    key
):
    try:

        pyautogui.press(
            str(key)
        )

        return True

    except Exception:
        return False


# =========================================================
# 61. HOTKEY
# =========================================================

def hotkey(
    *keys
):
    try:

        pyautogui.hotkey(
            *keys
        )

        return True

    except Exception:
        return False


# =========================================================
# 62. MOUSE CLICK
# =========================================================

def click(
    x=None,
    y=None,
    button="left"
):
    try:

        if x is None or y is None:

            pyautogui.click(
                button=button
            )

        else:

            pyautogui.click(
                int(x),
                int(y),
                button=button
            )

        return True

    except Exception:
        return False


# =========================================================
# 63. DOUBLE CLICK
# =========================================================

def double_click(
    x=None,
    y=None,
    button="left"
):
    try:

        if x is None or y is None:

            pyautogui.doubleClick(
                button=button
            )

        else:

            pyautogui.doubleClick(
                int(x),
                int(y),
                button=button
            )

        return True

    except Exception:
        return False


# =========================================================
# 64. RIGHT CLICK
# =========================================================

def right_click(
    x=None,
    y=None
):
    return click(
        x,
        y,
        button="right"
    )


# =========================================================
# 65. MOVE MOUSE
# =========================================================

def move_mouse(
    x,
    y,
    duration=0.2
):
    try:

        pyautogui.moveTo(
            int(x),
            int(y),
            duration=float(
                duration
            )
        )

        return True

    except Exception:
        return False


# =========================================================
# 66. SCROLL
# =========================================================

def scroll(
    amount
):
    try:

        pyautogui.scroll(
            int(amount)
        )

        return True

    except Exception:
        return False


# =========================================================
# 67. SCREEN SIZE
# =========================================================

def get_screen_size():
    size = pyautogui.size()

    return {
        "width": size.width,
        "height": size.height
    }


# =========================================================
# 68. MOUSE POSITION
# =========================================================

def get_mouse_position():
    position = (
        pyautogui.position()
    )

    return {
        "x": position.x,
        "y": position.y
    }


# =========================================================
# 69. SCREENSHOT
# =========================================================

def take_screenshot(
    filename=None
):
    try:

        if not filename:

            filename = (
                f"maya_screenshot_"
                f"{int(time.time())}.png"
            )

        screenshot = (
            pyautogui.screenshot()
        )

        screenshot.save(
            filename
        )

        return {
            "success": True,
            "file": filename
        }

    except Exception as error:

        return {
            "success": False,
            "message":
                str(error)
        }


# =========================================================
# 70. CLIPBOARD COPY
# =========================================================

def copy_to_clipboard(
    text
):
    try:

        win32clipboard.OpenClipboard()

        win32clipboard.EmptyClipboard()

        win32clipboard.SetClipboardText(
            str(text),
            win32con.CF_UNICODETEXT
        )

        win32clipboard.CloseClipboard()

        return True

    except Exception:

        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

        return False


# =========================================================
# 71. CLIPBOARD READ
# =========================================================

def read_clipboard():
    try:

        win32clipboard.OpenClipboard()

        text = (
            win32clipboard.GetClipboardData(
                win32con.CF_UNICODETEXT
            )
        )

        win32clipboard.CloseClipboard()

        return text

    except Exception:

        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

        return ""


# =========================================================
# 72. APP STATUS
# =========================================================

def app_status(
    app_name
):
    return {
        "app":
            app_name,

        "installed_match":
            find_installed_app(
                app_name
            ),

        "running":
            is_app_running(
                app_name
            ),

        "processes":
            find_processes(
                app_name
            ),

        "windows":
            find_windows(
                app_name
            )
    }


# =========================================================
# 73. VERIFY WINDOW STATE
# =========================================================

def verify_window_exists(
    title
):
    return bool(
        find_windows(
            title
        )
    )


# =========================================================
# 74. FULLSCREEN HELPER
# =========================================================

def fullscreen_active_app():
    try:

        pyautogui.press(
            "f11"
        )

        return True

    except Exception:
        return False


# =========================================================
# 75. SWITCH APP
# =========================================================

def switch_app():
    try:

        pyautogui.hotkey(
            "alt",
            "tab"
        )

        return True

    except Exception:
        return False


# =========================================================
# 76. CENTRAL APP ACTION ROUTER
# =========================================================

def execute_app_action(
    action,
    **kwargs
):
    """
    Main interface for controller.py.

    Brain/controller can use this one function
    for most app actions.
    """

    action = normalize_text(
        action
    )

    actions = {

        "refresh_apps":
            lambda:
                refresh_app_cache(),

        "find_app":
            lambda:
                find_installed_app(
                    kwargs.get("app")
                ),

        "search_apps":
            lambda:
                search_apps(
                    kwargs.get(
                        "query",
                        ""
                    )
                ),

        "open":
            lambda:
                open_app(
                    kwargs.get("app"),
                    kwargs.get(
                        "arguments"
                    )
                ),

        "close":
            lambda:
                close_app(
                    kwargs.get("app")
                ),

        "kill":
            lambda:
                kill_app(
                    kwargs.get("app")
                ),

        "restart":
            lambda:
                restart_app(
                    kwargs.get("app")
                ),

        "suspend":
            lambda:
                suspend_app(
                    kwargs.get("app")
                ),

        "resume":
            lambda:
                resume_app(
                    kwargs.get("app")
                ),

        "focus":
            lambda:
                focus_window(
                    kwargs.get("title"),
                    kwargs.get(
                        "index",
                        0
                    )
                ),

        "maximize":
            lambda:
                maximize_window(
                    kwargs.get("title")
                ),

        "minimize":
            lambda:
                minimize_window(
                    kwargs.get("title")
                ),

        "restore":
            lambda:
                restore_window(
                    kwargs.get("title")
                ),

        "move":
            lambda:
                move_window(
                    kwargs.get("title"),
                    kwargs.get("x"),
                    kwargs.get("y")
                ),

        "resize":
            lambda:
                resize_window(
                    kwargs.get("title"),
                    kwargs.get("width"),
                    kwargs.get("height")
                ),

        "left_half":
            lambda:
                move_window_left(
                    kwargs.get("title")
                ),

        "right_half":
            lambda:
                move_window_right(
                    kwargs.get("title")
                ),

        "always_on_top":
            lambda:
                set_always_on_top(
                    kwargs.get("title"),
                    kwargs.get(
                        "enabled",
                        True
                    )
                ),

        "open_path":
            lambda:
                open_path(
                    kwargs.get("path")
                ),

        "open_with":
            lambda:
                open_with_app(
                    kwargs.get("path"),
                    kwargs.get("app")
                ),

        "open_url":
            lambda:
                open_url(
                    kwargs.get("url"),
                    kwargs.get("browser")
                ),

        "type":
            lambda:
                type_text(
                    kwargs.get(
                        "text",
                        ""
                    )
                ),

        "press":
            lambda:
                press_key(
                    kwargs.get("key")
                ),

        "hotkey":
            lambda:
                hotkey(
                    *kwargs.get(
                        "keys",
                        []
                    )
                ),

        "click":
            lambda:
                click(
                    kwargs.get("x"),
                    kwargs.get("y"),
                    kwargs.get(
                        "button",
                        "left"
                    )
                ),

        "double_click":
            lambda:
                double_click(
                    kwargs.get("x"),
                    kwargs.get("y")
                ),

        "right_click":
            lambda:
                right_click(
                    kwargs.get("x"),
                    kwargs.get("y")
                ),

        "move_mouse":
            lambda:
                move_mouse(
                    kwargs.get("x"),
                    kwargs.get("y"),
                    kwargs.get(
                        "duration",
                        0.2
                    )
                ),

        "scroll":
            lambda:
                scroll(
                    kwargs.get(
                        "amount",
                        0
                    )
                ),

        "ui_click":
            lambda:
                ui_click(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "control_type"
                    ),
                    kwargs.get(
                        "automation_id"
                    )
                ),

        "ui_double_click":
            lambda:
                ui_double_click(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "control_type"
                    ),
                    kwargs.get(
                        "automation_id"
                    )
                ),

        "ui_right_click":
            lambda:
                ui_right_click(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "control_type"
                    ),
                    kwargs.get(
                        "automation_id"
                    )
                ),

        "ui_type":
            lambda:
                ui_type(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "text",
                        ""
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "control_type",
                        "Edit"
                    ),
                    kwargs.get(
                        "automation_id"
                    ),
                    kwargs.get(
                        "clear_first",
                        False
                    )
                ),

        "ui_read":
            lambda:
                ui_read_text(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "control_type"
                    ),
                    kwargs.get(
                        "automation_id"
                    )
                ),

        "ui_toggle":
            lambda:
                ui_toggle(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "control_title"
                    ),
                    kwargs.get(
                        "automation_id"
                    )
                ),

        "ui_select":
            lambda:
                ui_select(
                    kwargs.get(
                        "window_title"
                    ),
                    kwargs.get(
                        "item_text"
                    )
                ),

        "clipboard_copy":
            lambda:
                copy_to_clipboard(
                    kwargs.get(
                        "text",
                        ""
                    )
                ),

        "clipboard_read":
            lambda:
                read_clipboard(),

        "screenshot":
            lambda:
                take_screenshot(
                    kwargs.get(
                        "filename"
                    )
                ),

        "active_window":
            lambda:
                get_active_window(),

        "windows":
            lambda:
                get_all_windows(),

        "status":
            lambda:
                app_status(
                    kwargs.get("app")
                ),

        "fullscreen":
            lambda:
                fullscreen_active_app(),

        "switch_app":
            lambda:
                switch_app()
    }

    handler = actions.get(
        action
    )

    if not handler:

        return {
            "success": False,
            "message":
                f"Unknown app action: {action}"
        }

    try:

        result = handler()

        if isinstance(
            result,
            dict
        ):
            return result

        return {
            "success":
                bool(result),

            "result":
                result
        }

    except Exception as error:

        return {
            "success": False,
            "message":
                str(error)
        }


# =========================================================
# 77. MODULE STATUS
# =========================================================

def apps_module_status():
    return {
        "status": "ready",

        "cached_apps":
            len(
                load_app_cache()
            ),

        "features": {
            "app_discovery": True,
            "start_menu": True,
            "registry": True,
            "uwp_apps": True,
            "fuzzy_matching": True,
            "window_control": True,
            "process_control": True,
            "uia": True,
            "keyboard": True,
            "mouse": True,
            "clipboard": True,
            "screenshots": True
        }
    }
