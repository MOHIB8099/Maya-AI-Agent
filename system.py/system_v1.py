import os
import sys
import socket
import ctypes
import platform
import subprocess
import datetime
import time
from pathlib import Path

import psutil
import screen_brightness_control as sbc
import wmi

from pycaw.pycaw import AudioUtilities

# =========================================================
# 1. SETTINGS
# =========================================================

DEFAULT_TIMEOUT = 20


# =========================================================
# 2. BASIC RESULT HELPER
# =========================================================

def result(
    success,
    message="",
    **data
):
    response = {
        "success": bool(success),
        "message": message
    }

    response.update(data)

    return response


# =========================================================
# 3. ADMIN CHECK
# =========================================================

def is_admin():
    try:
        return bool(
            ctypes.windll.shell32.IsUserAnAdmin()
        )
    except Exception:
        return False


# =========================================================
# 4. RUN POWERSHELL
# =========================================================

def run_powershell(
    command,
    timeout=DEFAULT_TIMEOUT
):
    try:

        process = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command
            ],
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "success":
                process.returncode == 0,

            "stdout":
                process.stdout.strip(),

            "stderr":
                process.stderr.strip(),

            "returncode":
                process.returncode
        }

    except Exception as error:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(error),
            "returncode": -1
        }


# =========================================================
# 5. RUN CMD COMMAND
# =========================================================

def run_command(
    command,
    timeout=DEFAULT_TIMEOUT
):
    try:

        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "success":
                process.returncode == 0,

            "stdout":
                process.stdout.strip(),

            "stderr":
                process.stderr.strip(),

            "returncode":
                process.returncode
        }

    except Exception as error:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(error),
            "returncode": -1
        }


# =========================================================
# 6. SYSTEM INFORMATION
# =========================================================

def get_system_info():
    try:

        return {
            "success": True,

            "computer_name":
                socket.gethostname(),

            "os":
                platform.system(),

            "os_version":
                platform.version(),

            "release":
                platform.release(),

            "architecture":
                platform.machine(),

            "processor":
                platform.processor(),

            "python_version":
                platform.python_version(),

            "admin":
                is_admin()
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 7. CPU INFORMATION
# =========================================================

def get_cpu_info():
    try:

        frequency = psutil.cpu_freq()

        return {
            "success": True,

            "physical_cores":
                psutil.cpu_count(
                    logical=False
                ),

            "logical_cores":
                psutil.cpu_count(
                    logical=True
                ),

            "cpu_percent":
                psutil.cpu_percent(
                    interval=1
                ),

            "frequency_mhz":
                (
                    round(
                        frequency.current,
                        2
                    )
                    if frequency
                    else None
                )
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 8. RAM INFORMATION
# =========================================================

def get_ram_info():
    try:

        memory = psutil.virtual_memory()

        return {
            "success": True,

            "total_gb":
                round(
                    memory.total
                    / 1024**3,
                    2
                ),

            "used_gb":
                round(
                    memory.used
                    / 1024**3,
                    2
                ),

            "available_gb":
                round(
                    memory.available
                    / 1024**3,
                    2
                ),

            "percent":
                memory.percent
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 9. DISK INFORMATION
# =========================================================

def get_disk_info():
    disks = []

    try:

        for partition in psutil.disk_partitions():

            try:

                usage = psutil.disk_usage(
                    partition.mountpoint
                )

                disks.append(
                    {
                        "device":
                            partition.device,

                        "mountpoint":
                            partition.mountpoint,

                        "filesystem":
                            partition.fstype,

                        "total_gb":
                            round(
                                usage.total
                                / 1024**3,
                                2
                            ),

                        "used_gb":
                            round(
                                usage.used
                                / 1024**3,
                                2
                            ),

                        "free_gb":
                            round(
                                usage.free
                                / 1024**3,
                                2
                            ),

                        "percent":
                            usage.percent
                    }
                )

            except Exception:
                continue

        return {
            "success": True,
            "drives": disks
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 10. BATTERY INFORMATION
# =========================================================

def get_battery_info():
    try:

        battery = psutil.sensors_battery()

        if battery is None:

            return result(
                False,
                "Battery information not available."
            )

        return {
            "success": True,

            "percent":
                battery.percent,

            "plugged_in":
                battery.power_plugged,

            "seconds_left":
                battery.secsleft
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 11. MASTER AUDIO ENDPOINT
# =========================================================

def get_audio_endpoint():
    device = AudioUtilities.GetSpeakers()

    if hasattr(device, "EndpointVolume"):
        return device.EndpointVolume

    raise RuntimeError(
        "Windows audio endpoint volume is not available."
    )

# =========================================================
# 12. GET VOLUME
# =========================================================

def get_volume():
    try:

        endpoint = get_audio_endpoint()

        value = (
            endpoint
            .GetMasterVolumeLevelScalar()
        )

        muted = bool(
            endpoint.GetMute()
        )

        return {
            "success": True,

            "volume":
                round(
                    value * 100
                ),

            "muted":
                muted
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 13. SET EXACT VOLUME
# =========================================================

def set_volume(
    percent
):
    try:

        percent = float(
            percent
        )

        percent = max(
            0,
            min(
                100,
                percent
            )
        )

        endpoint = get_audio_endpoint()

        endpoint.SetMasterVolumeLevelScalar(
            percent / 100,
            None
        )

        check = get_volume()

        return {
            "success":
                check.get("success"),

            "message":
                f"Volume set to {round(percent)}%",

            "volume":
                check.get("volume")
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 14. VOLUME UP / DOWN
# =========================================================

def volume_up(
    amount=10
):
    current = get_volume()

    if not current.get(
        "success"
    ):
        return current

    return set_volume(
        current["volume"]
        + float(amount)
    )


def volume_down(
    amount=10
):
    current = get_volume()

    if not current.get(
        "success"
    ):
        return current

    return set_volume(
        current["volume"]
        - float(amount)
    )


# =========================================================
# 15. MUTE / UNMUTE
# =========================================================

def mute_volume():
    try:

        endpoint = get_audio_endpoint()

        endpoint.SetMute(
            1,
            None
        )

        return result(
            True,
            "Volume muted."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


def unmute_volume():
    try:

        endpoint = get_audio_endpoint()

        endpoint.SetMute(
            0,
            None
        )

        return result(
            True,
            "Volume unmuted."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


def toggle_mute():
    try:

        endpoint = get_audio_endpoint()

        current = bool(
            endpoint.GetMute()
        )

        endpoint.SetMute(
            int(
                not current
            ),
            None
        )

        return {
            "success": True,
            "muted": not current
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 16. GET BRIGHTNESS
# =========================================================

def get_brightness():
    try:

        brightness = sbc.get_brightness()

        return {
            "success": True,
            "brightness":
                brightness
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 17. SET BRIGHTNESS
# =========================================================

def set_brightness(
    percent
):
    try:

        percent = int(
            percent
        )

        percent = max(
            0,
            min(
                100,
                percent
            )
        )

        sbc.set_brightness(
            percent
        )

        return {
            "success": True,
            "message":
                f"Brightness set to {percent}%",

            "brightness":
                percent
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 18. BRIGHTNESS UP / DOWN
# =========================================================

def brightness_up(
    amount=10
):
    current = get_brightness()

    if not current.get(
        "success"
    ):
        return current

    values = current.get(
        "brightness",
        []
    )

    if not values:
        return result(
            False,
            "Brightness unavailable."
        )

    return set_brightness(
        values[0]
        + int(amount)
    )


def brightness_down(
    amount=10
):
    current = get_brightness()

    if not current.get(
        "success"
    ):
        return current

    values = current.get(
        "brightness",
        []
    )

    if not values:
        return result(
            False,
            "Brightness unavailable."
        )

    return set_brightness(
        values[0]
        - int(amount)
    )


# =========================================================
# 19. NETWORK INTERFACES
# =========================================================

def get_network_interfaces():
    try:

        interfaces = []

        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()

        for name in addresses:

            info = {
                "name": name,
                "up":
                    (
                        stats[name].isup
                        if name in stats
                        else None
                    ),

                "addresses": []
            }

            for address in addresses[name]:

                info[
                    "addresses"
                ].append(
                    {
                        "family":
                            str(
                                address.family
                            ),

                        "address":
                            address.address,

                        "netmask":
                            address.netmask
                    }
                )

            interfaces.append(
                info
            )

        return {
            "success": True,
            "interfaces":
                interfaces
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 20. LOCAL IP
# =========================================================

def get_local_ip():
    try:

        hostname = socket.gethostname()

        ip = socket.gethostbyname(
            hostname
        )

        return {
            "success": True,
            "hostname":
                hostname,

            "ip":
                ip
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 21. DNS INFORMATION
# =========================================================

def get_dns_info():
    command = (
        "Get-DnsClientServerAddress | "
        "Select-Object InterfaceAlias,"
        "AddressFamily,ServerAddresses | "
        "ConvertTo-Json -Depth 4"
    )

    return run_powershell(
        command
    )


# =========================================================
# 22. WIFI STATUS
# =========================================================

def get_wifi_status():
    response = run_command(
        "netsh wlan show interfaces"
    )

    return response


# =========================================================
# 23. WIFI ON
# =========================================================

def wifi_on(
    interface_name="Wi-Fi"
):
    command = (
        f'netsh interface set interface '
        f'name="{interface_name}" '
        f'admin=enabled'
    )

    output = run_command(
        command
    )

    output[
        "admin_required"
    ] = not is_admin()

    return output


# =========================================================
# 24. WIFI OFF
# =========================================================

def wifi_off(
    interface_name="Wi-Fi"
):
    command = (
        f'netsh interface set interface '
        f'name="{interface_name}" '
        f'admin=disabled'
    )

    output = run_command(
        command
    )

    output[
        "admin_required"
    ] = not is_admin()

    return output


# =========================================================
# 25. WIFI CONNECT
# =========================================================

def wifi_connect(
    profile_name
):
    if not profile_name:

        return result(
            False,
            "Wi-Fi profile name required."
        )

    return run_command(
        f'netsh wlan connect name="{profile_name}"'
    )


# =========================================================
# 26. WIFI DISCONNECT
# =========================================================

def wifi_disconnect():
    return run_command(
        "netsh wlan disconnect"
    )


# =========================================================
# 27. WIFI SAVED PROFILES
# =========================================================

def get_wifi_profiles():
    return run_command(
        "netsh wlan show profiles"
    )


# =========================================================
# 28. BLUETOOTH DEVICES
# =========================================================

def get_bluetooth_devices():
    command = (
        "Get-PnpDevice -Class Bluetooth | "
        "Select-Object Status,FriendlyName,"
        "InstanceId | "
        "ConvertTo-Json -Depth 3"
    )

    return run_powershell(
        command
    )


# =========================================================
# 29. BLUETOOTH ON
# =========================================================

def bluetooth_on():
    if not is_admin():

        return result(
            False,
            "Bluetooth control requires Administrator permission.",
            admin_required=True
        )

    command = (
        "Get-PnpDevice -Class Bluetooth | "
        "Where-Object {$_.Status -ne 'OK'} | "
        "Enable-PnpDevice -Confirm:$false"
    )

    return run_powershell(
        command
    )


# =========================================================
# 30. BLUETOOTH OFF
# =========================================================

def bluetooth_off():
    if not is_admin():

        return result(
            False,
            "Bluetooth control requires Administrator permission.",
            admin_required=True
        )

    command = (
        "Get-PnpDevice -Class Bluetooth | "
        "Where-Object {$_.Status -eq 'OK'} | "
        "Disable-PnpDevice -Confirm:$false"
    )

    return run_powershell(
        command
    )


# =========================================================
# 31. OPEN BLUETOOTH SETTINGS
# =========================================================

def open_bluetooth_settings():
    try:

        os.startfile(
            "ms-settings:bluetooth"
        )

        return result(
            True,
            "Bluetooth settings opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 32. AIRPLANE MODE SETTINGS
# =========================================================

def open_airplane_mode_settings():
    try:

        os.startfile(
            "ms-settings:network-airplanemode"
        )

        return result(
            True,
            "Airplane mode settings opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 33. WINDOWS SETTINGS PAGES
# =========================================================

SETTINGS_PAGES = {
    "home":
        "ms-settings:",

    "bluetooth":
        "ms-settings:bluetooth",

    "wifi":
        "ms-settings:network-wifi",

    "network":
        "ms-settings:network",

    "display":
        "ms-settings:display",

    "sound":
        "ms-settings:sound",

    "storage":
        "ms-settings:storagesense",

    "battery":
        "ms-settings:batterysaver",

    "power":
        "ms-settings:powersleep",

    "apps":
        "ms-settings:appsfeatures",

    "startup":
        "ms-settings:startupapps",

    "windows update":
        "ms-settings:windowsupdate",

    "notifications":
        "ms-settings:notifications",

    "privacy":
        "ms-settings:privacy"
}


def open_settings(
    page="home"
):
    try:

        page = str(
            page
        ).strip().lower()

        uri = SETTINGS_PAGES.get(
            page,
            "ms-settings:"
        )

        os.startfile(
            uri
        )

        return result(
            True,
            f"Opened {page} settings."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 34. LOCK COMPUTER
# =========================================================

def lock_computer():
    try:

        ctypes.windll.user32.LockWorkStation()

        return result(
            True,
            "Computer locked."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 35. SHUTDOWN
# =========================================================

def shutdown_computer(
    confirm=False,
    delay=0
):
    if not confirm:

        return result(
            False,
            "Shutdown confirmation required.",
            confirmation_required=True
        )

    try:

        subprocess.Popen(
            [
                "shutdown",
                "/s",
                "/t",
                str(
                    int(delay)
                )
            ]
        )

        return result(
            True,
            "Shutdown command sent."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 36. RESTART
# =========================================================

def restart_computer(
    confirm=False,
    delay=0
):
    if not confirm:

        return result(
            False,
            "Restart confirmation required.",
            confirmation_required=True
        )

    try:

        subprocess.Popen(
            [
                "shutdown",
                "/r",
                "/t",
                str(
                    int(delay)
                )
            ]
        )

        return result(
            True,
            "Restart command sent."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 37. CANCEL SHUTDOWN
# =========================================================

def cancel_shutdown():
    return run_command(
        "shutdown /a"
    )


# =========================================================
# 38. LOG OFF
# =========================================================

def logoff_computer(
    confirm=False
):
    if not confirm:

        return result(
            False,
            "Logoff confirmation required.",
            confirmation_required=True
        )

    return run_command(
        "shutdown /l"
    )


# =========================================================
# 39. SLEEP
# =========================================================

def sleep_computer(
    confirm=False
):
    if not confirm:

        return result(
            False,
            "Sleep confirmation required.",
            confirmation_required=True
        )

    command = (
        "rundll32.exe "
        "powrprof.dll,SetSuspendState "
        "0,1,0"
    )

    return run_command(
        command
    )


# =========================================================
# 40. HIBERNATE
# =========================================================

def hibernate_computer(
    confirm=False
):
    if not confirm:

        return result(
            False,
            "Hibernate confirmation required.",
            confirmation_required=True
        )

    return run_command(
        "shutdown /h"
    )


# =========================================================
# 41. SYSTEM UPTIME
# =========================================================

def get_uptime():
    try:

        boot_time = datetime.datetime.fromtimestamp(
            psutil.boot_time()
        )

        now = datetime.datetime.now()

        uptime = now - boot_time

        return {
            "success": True,

            "boot_time":
                boot_time.isoformat(),

            "uptime_seconds":
                int(
                    uptime.total_seconds()
                )
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 42. WINDOWS SERVICES
# =========================================================

def get_services():
    services = []

    try:

        for service in psutil.win_service_iter():

            try:

                info = service.as_dict()

                services.append(
                    {
                        "name":
                            info.get("name"),

                        "display_name":
                            info.get(
                                "display_name"
                            ),

                        "status":
                            info.get("status"),

                        "start_type":
                            info.get(
                                "start_type"
                            )
                    }
                )

            except Exception:
                continue

        return {
            "success": True,
            "services":
                services
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 43. SERVICE STATUS
# =========================================================

def service_status(
    service_name
):
    try:

        service = psutil.win_service_get(
            service_name
        )

        return {
            "success": True,
            "service":
                service.as_dict()
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 44. START SERVICE
# =========================================================

def start_service(
    service_name
):
    if not is_admin():

        return result(
            False,
            "Administrator permission required.",
            admin_required=True
        )

    return run_command(
        f'sc start "{service_name}"'
    )


# =========================================================
# 45. STOP SERVICE
# =========================================================

def stop_service(
    service_name,
    confirm=False
):
    if not confirm:

        return result(
            False,
            "Service stop confirmation required.",
            confirmation_required=True
        )

    if not is_admin():

        return result(
            False,
            "Administrator permission required.",
            admin_required=True
        )

    return run_command(
        f'sc stop "{service_name}"'
    )


# =========================================================
# 46. RESTART SERVICE
# =========================================================

def restart_service(
    service_name,
    confirm=False
):
    if not confirm:

        return result(
            False,
            "Service restart confirmation required.",
            confirmation_required=True
        )

    stopped = stop_service(
        service_name,
        confirm=True
    )

    time.sleep(
        1
    )

    started = start_service(
        service_name
    )

    return {
        "success":
            (
                stopped.get("success")
                and
                started.get("success")
            ),

        "stop_result":
            stopped,

        "start_result":
            started
    }


# =========================================================
# 47. STARTUP PROGRAMS
# =========================================================

def get_startup_programs():
    command = (
        "Get-CimInstance Win32_StartupCommand | "
        "Select-Object Name,Command,Location,User | "
        "ConvertTo-Json -Depth 3"
    )

    return run_powershell(
        command
    )


# =========================================================
# 48. ENVIRONMENT VARIABLE READ
# =========================================================

def get_environment_variable(
    name
):
    value = os.getenv(
        str(name)
    )

    return {
        "success":
            value is not None,

        "name":
            name,

        "value":
            value
    }


# =========================================================
# 49. ENVIRONMENT VARIABLE SET
# =========================================================

def set_environment_variable(
    name,
    value,
    permanent=False
):
    try:

        if permanent:

            process = subprocess.run(
                [
                    "setx",
                    str(name),
                    str(value)
                ],
                capture_output=True,
                text=True
            )

            return {
                "success":
                    process.returncode == 0,

                "stdout":
                    process.stdout.strip(),

                "stderr":
                    process.stderr.strip()
            }

        os.environ[
            str(name)
        ] = str(value)

        return result(
            True,
            "Environment variable updated for current process."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 50. CURRENT DATE / TIME
# =========================================================

def get_current_datetime():
    now = datetime.datetime.now()

    return {
        "success": True,

        "datetime":
            now.isoformat(),

        "date":
            now.strftime(
                "%Y-%m-%d"
            ),

        "time":
            now.strftime(
                "%H:%M:%S"
            )
    }


# =========================================================
# 51. DEVICE MANAGER
# =========================================================

def open_device_manager():
    try:

        subprocess.Popen(
            [
                "devmgmt.msc"
            ],
            shell=True
        )

        return result(
            True,
            "Device Manager opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 52. CONTROL PANEL
# =========================================================

def open_control_panel():
    try:

        subprocess.Popen(
            [
                "control.exe"
            ]
        )

        return result(
            True,
            "Control Panel opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 53. TASK MANAGER
# =========================================================

def open_task_manager():
    try:

        subprocess.Popen(
            [
                "taskmgr.exe"
            ]
        )

        return result(
            True,
            "Task Manager opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 54. SYSTEM INFORMATION WINDOW
# =========================================================

def open_system_information():
    try:

        subprocess.Popen(
            [
                "msinfo32.exe"
            ]
        )

        return result(
            True,
            "System Information opened."
        )

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 55. WINDOWS UPDATE
# =========================================================

def open_windows_update():
    return open_settings(
        "windows update"
    )


# =========================================================
# 56. NETWORK RESET INFO
# =========================================================

def flush_dns():
    return run_command(
        "ipconfig /flushdns"
    )


def renew_ip():
    if not is_admin():

        return result(
            False,
            "Administrator permission required.",
            admin_required=True
        )

    return run_command(
        "ipconfig /renew"
    )


# =========================================================
# 57. PROCESS LIST
# =========================================================

def get_processes():
    processes = []

    for process in psutil.process_iter(
        [
            "pid",
            "name",
            "cpu_percent",
            "memory_percent"
        ]
    ):

        try:

            processes.append(
                {
                    "pid":
                        process.info["pid"],

                    "name":
                        process.info["name"],

                    "cpu_percent":
                        process.info[
                            "cpu_percent"
                        ],

                    "memory_percent":
                        round(
                            process.info[
                                "memory_percent"
                            ],
                            2
                        )
                }
            )

        except Exception:
            continue

    return {
        "success": True,
        "processes":
            processes
    }


# =========================================================
# 58. SYSTEM HEALTH SUMMARY
# =========================================================

def get_system_health():
    return {
        "success": True,

        "cpu":
            get_cpu_info(),

        "ram":
            get_ram_info(),

        "disk":
            get_disk_info(),

        "battery":
            get_battery_info(),

        "volume":
            get_volume(),

        "brightness":
            get_brightness(),

        "uptime":
            get_uptime()
    }


# =========================================================
# 59. CENTRAL SYSTEM ACTION ROUTER
# =========================================================

def execute_system_action(
    action,
    **kwargs
):
    """
    Main system.py interface for controller.py.
    """

    action = str(
        action
    ).strip().lower()

    actions = {

        "system_info":
            lambda:
                get_system_info(),

        "cpu":
            lambda:
                get_cpu_info(),

        "ram":
            lambda:
                get_ram_info(),

        "disk":
            lambda:
                get_disk_info(),

        "battery":
            lambda:
                get_battery_info(),

        "health":
            lambda:
                get_system_health(),

        "get_volume":
            lambda:
                get_volume(),

        "set_volume":
            lambda:
                set_volume(
                    kwargs.get(
                        "percent",
                        50
                    )
                ),

        "volume_up":
            lambda:
                volume_up(
                    kwargs.get(
                        "amount",
                        10
                    )
                ),

        "volume_down":
            lambda:
                volume_down(
                    kwargs.get(
                        "amount",
                        10
                    )
                ),

        "mute":
            lambda:
                mute_volume(),

        "unmute":
            lambda:
                unmute_volume(),

        "toggle_mute":
            lambda:
                toggle_mute(),

        "get_brightness":
            lambda:
                get_brightness(),

        "set_brightness":
            lambda:
                set_brightness(
                    kwargs.get(
                        "percent",
                        50
                    )
                ),

        "brightness_up":
            lambda:
                brightness_up(
                    kwargs.get(
                        "amount",
                        10
                    )
                ),

        "brightness_down":
            lambda:
                brightness_down(
                    kwargs.get(
                        "amount",
                        10
                    )
                ),

        "network":
            lambda:
                get_network_interfaces(),

        "local_ip":
            lambda:
                get_local_ip(),

        "dns":
            lambda:
                get_dns_info(),

        "wifi_status":
            lambda:
                get_wifi_status(),

        "wifi_on":
            lambda:
                wifi_on(
                    kwargs.get(
                        "interface",
                        "Wi-Fi"
                    )
                ),

        "wifi_off":
            lambda:
                wifi_off(
                    kwargs.get(
                        "interface",
                        "Wi-Fi"
                    )
                ),

        "wifi_connect":
            lambda:
                wifi_connect(
                    kwargs.get(
                        "profile"
                    )
                ),

        "wifi_disconnect":
            lambda:
                wifi_disconnect(),

        "wifi_profiles":
            lambda:
                get_wifi_profiles(),

        "bluetooth_devices":
            lambda:
                get_bluetooth_devices(),

        "bluetooth_on":
            lambda:
                bluetooth_on(),

        "bluetooth_off":
            lambda:
                bluetooth_off(),

        "bluetooth_settings":
            lambda:
                open_bluetooth_settings(),

        "airplane_settings":
            lambda:
                open_airplane_mode_settings(),

        "settings":
            lambda:
                open_settings(
                    kwargs.get(
                        "page",
                        "home"
                    )
                ),

        "lock":
            lambda:
                lock_computer(),

        "shutdown":
            lambda:
                shutdown_computer(
                    kwargs.get(
                        "confirm",
                        False
                    ),
                    kwargs.get(
                        "delay",
                        0
                    )
                ),

        "restart":
            lambda:
                restart_computer(
                    kwargs.get(
                        "confirm",
                        False
                    ),
                    kwargs.get(
                        "delay",
                        0
                    )
                ),

        "cancel_shutdown":
            lambda:
                cancel_shutdown(),

        "sleep":
            lambda:
                sleep_computer(
                    kwargs.get(
                        "confirm",
                        False
                    )
                ),

        "hibernate":
            lambda:
                hibernate_computer(
                    kwargs.get(
                        "confirm",
                        False
                    )
                ),

        "logoff":
            lambda:
                logoff_computer(
                    kwargs.get(
                        "confirm",
                        False
                    )
                ),

        "services":
            lambda:
                get_services(),

        "service_status":
            lambda:
                service_status(
                    kwargs.get(
                        "service"
                    )
                ),

        "start_service":
            lambda:
                start_service(
                    kwargs.get(
                        "service"
                    )
                ),

        "stop_service":
            lambda:
                stop_service(
                    kwargs.get(
                        "service"
                    ),
                    kwargs.get(
                        "confirm",
                        False
                    )
                ),

        "restart_service":
            lambda:
                restart_service(
                    kwargs.get(
                        "service"
                    ),
                    kwargs.get(
                        "confirm",
                        False
                    )
                ),

        "startup":
            lambda:
                get_startup_programs(),

        "datetime":
            lambda:
                get_current_datetime(),

        "device_manager":
            lambda:
                open_device_manager(),

        "control_panel":
            lambda:
                open_control_panel(),

        "task_manager":
            lambda:
                open_task_manager(),

        "system_information":
            lambda:
                open_system_information(),

        "windows_update":
            lambda:
                open_windows_update(),

        "flush_dns":
            lambda:
                flush_dns(),

        "renew_ip":
            lambda:
                renew_ip(),

        "processes":
            lambda:
                get_processes(),

        "admin":
            lambda:
                {
                    "success": True,
                    "admin":
                        is_admin()
                }
    }

    handler = actions.get(
        action
    )

    if not handler:

        return result(
            False,
            f"Unknown system action: {action}"
        )

    try:

        response = handler()

        if isinstance(
            response,
            dict
        ):
            return response

        return {
            "success":
                bool(response),

            "result":
                response
        }

    except Exception as error:

        return result(
            False,
            str(error)
        )


# =========================================================
# 60. MODULE STATUS
# =========================================================

def system_module_status():
    return {
        "status": "ready",

        "admin":
            is_admin(),

        "features": {
            "volume":
                True,

            "brightness":
                True,

            "wifi":
                True,

            "bluetooth":
                True,

            "battery":
                True,

            "power":
                True,

            "cpu":
                True,

            "ram":
                True,

            "storage":
                True,

            "network":
                True,

            "services":
                True,

            "startup":
                True,

            "windows_settings":
                True,

            "diagnostics":
                True
        }
    }
