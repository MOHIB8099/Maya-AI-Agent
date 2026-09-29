"""
Maya AI Agent - File Control V1

Single module containing four layers:
1. Search & Info
2. File Operations
3. Smart Tools
4. Safety & Logs

This module is intentionally standalone. It can be connected to controller.py
later through execute_file_action().
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


# ============================================================
# CONFIGURATION
# ============================================================

MODULE_VERSION = "1.0.0"
LOG_FILE = Path.home() / ".maya_file_control_log.json"
MAX_LOG_ENTRIES = 500

PROTECTED_PATH_NAMES = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "system volume information",
}

# These locations are allowed for normal Maya file work.
COMMON_LOCATIONS = {
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "pictures": Path.home() / "Pictures",
    "videos": Path.home() / "Videos",
    "music": Path.home() / "Music",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _expand_path(value: str | os.PathLike[str]) -> Path:
    """Expand ~ and environment variables and return an absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve()


def _resolve_common_location(value: str | os.PathLike[str]) -> Path:
    text = str(value).strip().lower()
    return COMMON_LOCATIONS.get(text, _expand_path(value))


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _safe_relative(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_protected_path(path: str | os.PathLike[str]) -> bool:
    """Return True for Windows/system locations or their direct children."""
    try:
        p = _expand_path(path)
    except Exception:
        return True

    parts = {part.lower() for part in p.parts}
    if any(name in parts for name in PROTECTED_PATH_NAMES):
        return True

    # Protect the filesystem root itself.
    if p == Path(p.anchor):
        return True

    return False


def _ensure_safe_target(path: Path, *, destructive: bool = False) -> None:
    if destructive and is_protected_path(path):
        raise PermissionError(f"Protected system path: {path}")


def _unique_path(path: Path) -> Path:
    """Create a non-conflicting path such as file (1).txt."""
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 1

    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _log(action: str, success: bool, **details: Any) -> dict[str, Any]:
    entry = {
        "timestamp": _now(),
        "action": action,
        "success": bool(success),
        "details": details,
    }

    try:
        entries = []
        if LOG_FILE.exists():
            with LOG_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, list):
                    entries = data
        entries.append(entry)
        entries = entries[-MAX_LOG_ENTRIES:]
        with LOG_FILE.open("w", encoding="utf-8") as file:
            json.dump(entries, file, indent=2, ensure_ascii=False, default=str)
    except Exception:
        # Logging must never break the actual file operation.
        pass

    return entry


def _success(action: str, **data: Any) -> dict[str, Any]:
    _log(action, True, **data)
    return {"success": True, "action": action, **data}


def _failure(action: str, error: Exception | str, **data: Any) -> dict[str, Any]:
    message = str(error)
    _log(action, False, error=message, **data)
    return {"success": False, "action": action, "message": message, **data}


# ============================================================
# LAYER 1 - SEARCH & INFO
# ============================================================


def search_files(
    path: str = ".",
    query: str = "",
    extension: str = "",
    recursive: bool = True,
    max_results: int = 100,
    min_size: int | None = None,
    max_size: int | None = None,
) -> dict[str, Any]:
    """Search files by name, extension and optional size limits."""
    try:
        root = _resolve_common_location(path)
        if not root.exists():
            return _failure("search_files", f"Path does not exist: {root}")
        if not root.is_dir():
            return _failure("search_files", f"Not a folder: {root}")

        query_lower = str(query or "").strip().lower()
        ext = str(extension or "").strip().lower()
        if ext and not ext.startswith("."):
            ext = "." + ext

        iterator: Iterable[Path] = root.rglob("*") if recursive else root.glob("*")
        results = []

        for item in iterator:
            try:
                if not item.is_file():
                    continue
                if query_lower and query_lower not in item.name.lower():
                    continue
                if ext and item.suffix.lower() != ext:
                    continue

                stat = item.stat()
                if min_size is not None and stat.st_size < int(min_size):
                    continue
                if max_size is not None and stat.st_size > int(max_size):
                    continue

                results.append({
                    "name": item.name,
                    "path": str(item),
                    "extension": item.suffix.lower(),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                })

                if len(results) >= max(1, int(max_results)):
                    break
            except (PermissionError, OSError):
                continue

        return _success("search_files", path=str(root), count=len(results), results=results)
    except Exception as error:
        return _failure("search_files", error)


def list_folder(path: str = ".", recursive: bool = False, max_results: int = 500) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        if not root.exists() or not root.is_dir():
            return _failure("list_folder", f"Folder not found: {root}")

        iterator = root.rglob("*") if recursive else root.iterdir()
        items = []
        for item in iterator:
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "folder" if item.is_dir() else "file",
                    "size": stat.st_size if item.is_file() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                })
                if len(items) >= max(1, int(max_results)):
                    break
            except (PermissionError, OSError):
                continue

        return _success("list_folder", path=str(root), count=len(items), items=items)
    except Exception as error:
        return _failure("list_folder", error)


def get_file_info(path: str) -> dict[str, Any]:
    try:
        target = _expand_path(path)
        if not _path_exists(target):
            return _failure("get_file_info", f"Path not found: {target}")

        stat = target.stat()
        return _success(
            "get_file_info",
            name=target.name,
            path=str(target),
            type="folder" if target.is_dir() else "file",
            extension=target.suffix.lower() if target.is_file() else "",
            size=stat.st_size if target.is_file() else None,
            created=datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(timespec="seconds"),
            modified=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            accessed=datetime.fromtimestamp(stat.st_atime).astimezone().isoformat(timespec="seconds"),
            read_only=not os.access(target, os.W_OK),
        )
    except Exception as error:
        return _failure("get_file_info", error)


def find_large_files(path: str = ".", min_size_mb: float = 100, max_results: int = 50) -> dict[str, Any]:
    return search_files(
        path=path,
        min_size=int(float(min_size_mb) * 1024 * 1024),
        recursive=True,
        max_results=max_results,
    )


def find_recent_files(path: str = ".", days: int = 7, max_results: int = 100) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        cutoff = time.time() - max(0, int(days)) * 86400
        results = []
        for item in root.rglob("*"):
            try:
                if item.is_file() and item.stat().st_mtime >= cutoff:
                    results.append({
                        "name": item.name,
                        "path": str(item),
                        "modified": datetime.fromtimestamp(item.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
                        "size": item.stat().st_size,
                    })
                    if len(results) >= max(1, int(max_results)):
                        break
            except (PermissionError, OSError):
                continue

        results.sort(key=lambda x: x["modified"], reverse=True)
        return _success("find_recent_files", path=str(root), count=len(results), results=results)
    except Exception as error:
        return _failure("find_recent_files", error)


def calculate_folder_size(path: str) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        if not root.is_dir():
            return _failure("calculate_folder_size", f"Not a folder: {root}")

        total = 0
        file_count = 0
        folder_count = 0
        for item in root.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
                    file_count += 1
                elif item.is_dir():
                    folder_count += 1
            except (PermissionError, OSError):
                continue

        return _success(
            "calculate_folder_size",
            path=str(root),
            bytes=total,
            megabytes=round(total / (1024 * 1024), 2),
            gigabytes=round(total / (1024 ** 3), 3),
            files=file_count,
            folders=folder_count,
        )
    except Exception as error:
        return _failure("calculate_folder_size", error)


def find_empty_folders(path: str = ".", max_results: int = 100) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        results = []
        for folder in root.rglob("*"):
            if not folder.is_dir():
                continue
            try:
                if not any(folder.iterdir()):
                    results.append(str(folder))
                    if len(results) >= max(1, int(max_results)):
                        break
            except (PermissionError, OSError):
                continue
        return _success("find_empty_folders", path=str(root), count=len(results), folders=results)
    except Exception as error:
        return _failure("find_empty_folders", error)


def _file_hash(path: Path, algorithm: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(path: str = ".", algorithm: str = "sha256", max_results: int = 100) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        groups: dict[tuple[int, str], list[str]] = {}
        for item in root.rglob("*"):
            try:
                if not item.is_file():
                    continue
                stat = item.stat()
                key = (stat.st_size, _file_hash(item, algorithm))
                groups.setdefault(key, []).append(str(item))
            except (PermissionError, OSError, ValueError):
                continue

        duplicates = [
            {"size": key[0], "hash": key[1], "files": paths}
            for key, paths in groups.items()
            if len(paths) > 1
        ]
        duplicates = duplicates[:max(1, int(max_results))]
        return _success("find_duplicates", path=str(root), count=len(duplicates), groups=duplicates)
    except Exception as error:
        return _failure("find_duplicates", error)


# ============================================================
# LAYER 2 - FILE OPERATIONS
# ============================================================


def create_folder(path: str) -> dict[str, Any]:
    try:
        target = _expand_path(path)
        target.mkdir(parents=True, exist_ok=True)
        return _success("create_folder", path=str(target))
    except Exception as error:
        return _failure("create_folder", error)


def create_file(path: str, content: str = "", overwrite: bool = False) -> dict[str, Any]:
    try:
        target = _expand_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            target = _unique_path(target)
        target.write_text(str(content), encoding="utf-8")
        return _success("create_file", path=str(target))
    except Exception as error:
        return _failure("create_file", error)


def copy_item(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    try:
        src = _expand_path(source)
        dest = _expand_path(destination)
        if not _path_exists(src):
            return _failure("copy", f"Source not found: {src}")
        _ensure_safe_target(src)

        if dest.exists() and dest.is_dir():
            dest = dest / src.name
        if dest.exists() and not overwrite:
            dest = _unique_path(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=overwrite)
        else:
            shutil.copy2(src, dest)
        return _success("copy", source=str(src), destination=str(dest))
    except Exception as error:
        return _failure("copy", error)


def move_item(source: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    try:
        src = _expand_path(source)
        dest = _expand_path(destination)
        if not _path_exists(src):
            return _failure("move", f"Source not found: {src}")
        _ensure_safe_target(src, destructive=True)
        _ensure_safe_target(dest.parent, destructive=True)

        if dest.exists() and dest.is_dir():
            dest = dest / src.name
        if dest.exists() and not overwrite:
            dest = _unique_path(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return _success("move", source=str(src), destination=str(dest))
    except Exception as error:
        return _failure("move", error)


def rename_item(path: str, new_name: str, overwrite: bool = False) -> dict[str, Any]:
    try:
        src = _expand_path(path)
        if not _path_exists(src):
            return _failure("rename", f"Path not found: {src}")
        _ensure_safe_target(src, destructive=True)

        name = Path(str(new_name)).name
        if not name or name in {".", ".."}:
            return _failure("rename", "Invalid new name.")

        dest = src.parent / name
        if dest.exists() and not overwrite:
            dest = _unique_path(dest)
        elif dest.exists() and overwrite:
            _ensure_safe_target(dest, destructive=True)

        src.rename(dest)
        return _success("rename", source=str(src), destination=str(dest))
    except Exception as error:
        return _failure("rename", error)


def delete_item(path: str, permanent: bool = False, confirm: bool = False) -> dict[str, Any]:
    """Delete safely. By default the item goes to Recycle Bin."""
    try:
        target = _expand_path(path)
        if not _path_exists(target):
            return _failure("delete", f"Path not found: {target}")
        if not confirm:
            return _failure("delete", "Confirmation required before deleting a file or folder.")

        _ensure_safe_target(target, destructive=True)

        if permanent:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return _success("delete", path=str(target), permanent=True)

        if send2trash is None:
            return _failure(
                "delete",
                "Recycle Bin support requires the 'send2trash' package. Use permanent=true only if you intentionally want permanent deletion.",
            )
        send2trash(str(target))
        return _success("delete", path=str(target), permanent=False, recycle_bin=True)
    except Exception as error:
        return _failure("delete", error)


def read_text_file(path: str, max_chars: int = 100_000) -> dict[str, Any]:
    try:
        target = _expand_path(path)
        if not target.is_file():
            return _failure("read_text_file", f"File not found: {target}")
        text = target.read_text(encoding="utf-8", errors="replace")
        return _success("read_text_file", path=str(target), text=text[:max_chars], truncated=len(text) > max_chars)
    except Exception as error:
        return _failure("read_text_file", error)


def write_text_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    try:
        target = _expand_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as file:
            file.write(str(content))
        return _success("write_text_file", path=str(target), append=append)
    except Exception as error:
        return _failure("write_text_file", error)


def zip_create(source: str, output_zip: str) -> dict[str, Any]:
    try:
        src = _expand_path(source)
        out = _expand_path(output_zip)
        if not _path_exists(src):
            return _failure("zip_create", f"Source not found: {src}")
        if out.suffix.lower() != ".zip":
            out = out.with_suffix(".zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out = _unique_path(out)

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            if src.is_file():
                archive.write(src, arcname=src.name)
            else:
                for item in src.rglob("*"):
                    if item.is_file():
                        archive.write(item, arcname=item.relative_to(src.parent))

        return _success("zip_create", source=str(src), output=str(out))
    except Exception as error:
        return _failure("zip_create", error)


def zip_extract(zip_path: str, destination: str, overwrite: bool = False) -> dict[str, Any]:
    try:
        archive_path = _expand_path(zip_path)
        dest = _expand_path(destination)
        if not archive_path.is_file() or archive_path.suffix.lower() != ".zip":
            return _failure("zip_extract", f"ZIP file not found: {archive_path}")

        dest.mkdir(parents=True, exist_ok=True)
        root = dest.resolve()

        with zipfile.ZipFile(archive_path, "r") as archive:
            for member in archive.infolist():
                member_path = (dest / member.filename).resolve()
                if not _safe_relative(member_path, root):
                    return _failure("zip_extract", "Unsafe ZIP path detected.")
            for member in archive.infolist():
                target = dest / member.filename
                if target.exists() and not overwrite:
                    if member.is_dir():
                        continue
                    target = _unique_path(target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                else:
                    archive.extract(member, dest)

        return _success("zip_extract", source=str(archive_path), destination=str(dest))
    except Exception as error:
        return _failure("zip_extract", error)


# ============================================================
# LAYER 3 - SMART TOOLS
# ============================================================


def batch_rename(path: str, pattern: str, replacement: str = "", extension: str = "", recursive: bool = False) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        if not root.is_dir():
            return _failure("batch_rename", f"Not a folder: {root}")

        ext = str(extension or "").strip().lower()
        if ext and not ext.startswith("."):
            ext = "." + ext

        iterator = root.rglob("*") if recursive else root.iterdir()
        changed = []
        for item in iterator:
            if not item.is_file():
                continue
            if ext and item.suffix.lower() != ext:
                continue
            if pattern not in item.name:
                continue

            new_name = item.name.replace(pattern, replacement)
            if new_name == item.name:
                continue
            dest = item.parent / new_name
            if dest.exists():
                dest = _unique_path(dest)
            _ensure_safe_target(item, destructive=True)
            item.rename(dest)
            changed.append({"old": str(item), "new": str(dest)})

        return _success("batch_rename", path=str(root), count=len(changed), changes=changed)
    except Exception as error:
        return _failure("batch_rename", error)


def organize_by_extension(path: str, copy: bool = False) -> dict[str, Any]:
    try:
        root = _resolve_common_location(path)
        if not root.is_dir():
            return _failure("organize_by_extension", f"Not a folder: {root}")

        moved = []
        for item in root.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lower().lstrip(".") or "no_extension"
            target_dir = root / ext
            target_dir.mkdir(exist_ok=True)
            destination = _unique_path(target_dir / item.name)
            if copy:
                shutil.copy2(item, destination)
            else:
                shutil.move(str(item), str(destination))
            moved.append({"source": str(item), "destination": str(destination)})

        return _success("organize_by_extension", path=str(root), copy=copy, count=len(moved), changes=moved)
    except Exception as error:
        return _failure("organize_by_extension", error)


def backup_item(source: str, destination: str) -> dict[str, Any]:
    try:
        src = _expand_path(source)
        dest = _expand_path(destination)
        if not _path_exists(src):
            return _failure("backup", f"Source not found: {src}")

        dest.mkdir(parents=True, exist_ok=True)
        target = dest / src.name
        if target.exists():
            target = _unique_path(target)

        if src.is_dir():
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)

        return _success("backup", source=str(src), destination=str(target))
    except Exception as error:
        return _failure("backup", error)


def compare_files(first: str, second: str, algorithm: str = "sha256") -> dict[str, Any]:
    try:
        a = _expand_path(first)
        b = _expand_path(second)
        if not a.is_file() or not b.is_file():
            return _failure("compare_files", "Both paths must be files.")
        hash_a = _file_hash(a, algorithm)
        hash_b = _file_hash(b, algorithm)
        return _success(
            "compare_files",
            first=str(a),
            second=str(b),
            algorithm=algorithm,
            identical=hash_a == hash_b,
            first_hash=hash_a,
            second_hash=hash_b,
        )
    except Exception as error:
        return _failure("compare_files", error)


def cleanup_empty_folders(path: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return _failure("cleanup_empty_folders", "Confirmation required before deleting folders.")
    found = find_empty_folders(path=path, max_results=10000)
    if not found.get("success"):
        return found

    removed = []
    for folder in sorted(found.get("folders", []), key=len, reverse=True):
        try:
            target = _expand_path(folder)
            _ensure_safe_target(target, destructive=True)
            target.rmdir()
            removed.append(str(target))
        except OSError:
            continue

    return _success("cleanup_empty_folders", count=len(removed), removed=removed)


def temporary_cleanup(path: str | None = None, older_than_days: int = 7, confirm: bool = False) -> dict[str, Any]:
    """Clean old files only inside the explicitly supplied folder."""
    if not confirm:
        return _failure("temporary_cleanup", "Confirmation required before cleanup.")
    if not path:
        return _failure("temporary_cleanup", "An explicit folder path is required.")

    try:
        root = _resolve_common_location(path)
        cutoff = time.time() - max(0, int(older_than_days)) * 86400
        removed = []
        for item in root.rglob("*"):
            try:
                if item.is_file() and item.stat().st_mtime < cutoff:
                    _ensure_safe_target(item, destructive=True)
                    if send2trash is not None:
                        send2trash(str(item))
                    else:
                        item.unlink()
                    removed.append(str(item))
            except (PermissionError, OSError):
                continue
        return _success("temporary_cleanup", path=str(root), count=len(removed), removed=removed)
    except Exception as error:
        return _failure("temporary_cleanup", error)


# ============================================================
# LAYER 4 - SAFETY & LOGS
# ============================================================


def get_action_log(limit: int = 50) -> dict[str, Any]:
    try:
        if not LOG_FILE.exists():
            return _success("get_action_log", count=0, entries=[])
        with LOG_FILE.open("r", encoding="utf-8") as file:
            entries = json.load(file)
        if not isinstance(entries, list):
            entries = []
        return _success("get_action_log", count=min(len(entries), int(limit)), entries=entries[-max(1, int(limit)):])
    except Exception as error:
        return _failure("get_action_log", error)


def clear_action_log(confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return _failure("clear_action_log", "Confirmation required before clearing the action log.")
    try:
        if LOG_FILE.exists():
            LOG_FILE.unlink()
        return _success("clear_action_log")
    except Exception as error:
        return _failure("clear_action_log", error)


def module_status() -> dict[str, Any]:
    return {
        "status": "ready",
        "module": "file_control",
        "version": MODULE_VERSION,
        "layers": [
            "search_and_info",
            "file_operations",
            "smart_tools",
            "safety_and_logs",
        ],
        "recycle_bin_support": send2trash is not None,
        "log_file": str(LOG_FILE),
    }


def execute_file_action(action: str, **kwargs: Any) -> dict[str, Any]:
    """Central router used later by Maya's controller."""
    if not action:
        return _failure("file_action", "File action name is missing.")

    action_name = str(action).strip().lower()

    routes = {
        # Layer 1
        "search": search_files,
        "search_files": search_files,
        "list": list_folder,
        "list_folder": list_folder,
        "info": get_file_info,
        "file_info": get_file_info,
        "large_files": find_large_files,
        "recent_files": find_recent_files,
        "folder_size": calculate_folder_size,
        "empty_folders": find_empty_folders,
        "duplicates": find_duplicates,
        # Layer 2
        "create_folder": create_folder,
        "mkdir": create_folder,
        "create_file": create_file,
        "copy": copy_item,
        "move": move_item,
        "rename": rename_item,
        "delete": delete_item,
        "read": read_text_file,
        "read_text": read_text_file,
        "write": write_text_file,
        "write_text": write_text_file,
        "zip": zip_create,
        "zip_create": zip_create,
        "extract": zip_extract,
        "zip_extract": zip_extract,
        # Layer 3
        "batch_rename": batch_rename,
        "organize": organize_by_extension,
        "organize_by_extension": organize_by_extension,
        "backup": backup_item,
        "compare": compare_files,
        "compare_files": compare_files,
        "cleanup_empty": cleanup_empty_folders,
        "cleanup_empty_folders": cleanup_empty_folders,
        "temporary_cleanup": temporary_cleanup,
        # Layer 4
        "log": get_action_log,
        "action_log": get_action_log,
        "clear_log": clear_action_log,
        "status": module_status,
    }

    handler = routes.get(action_name)
    if handler is None:
        return _failure("file_action", f"Unknown file action: {action_name}")

    try:
        return handler(**kwargs)
    except TypeError as error:
        return _failure(action_name, f"Invalid arguments: {error}")
    except Exception as error:
        return _failure(action_name, error)


if __name__ == "__main__":
    print(json.dumps(module_status(), indent=2, ensure_ascii=False))
