"""Dateizuordnung unter Linux: ``.pap``-Dateien per Doppelklick mit dem Programm öffnen.

Nach den freedesktop.org-Regeln, nur im Benutzerordner (keine Administratorrechte):

* ``~/.local/share/applications/bstechnik-papdesigner.desktop`` – Eintrag im Startmenü, startet das AppImage
* ``~/.local/share/mime/packages/bstechnik-papdesigner.xml`` – Dateityp ``application/x-bstechnik-pap`` (``*.pap``)
* ``~/.local/share/icons/hicolor/256x256/{apps,mimetypes}/…png`` – Programm- und Dateisymbol
* ``~/.config/mimeapps.list`` – das Programm als Standard für diesen Dateityp (nur diese eine Zeile)

Danach werden ``update-mime-database`` und ``update-desktop-database`` aufgerufen, falls vorhanden (gehören zu
praktisch jeder Desktop-Umgebung).

Das AppImage richtet das beim Start von selbst ein (``ensure_installed``), wenn es fehlt oder auf eine andere
AppImage-Datei bzw. Version zeigt (z. B. nach dem Verschieben oder einem Update). Über das Menü „Hilfe“ lässt
es sich jederzeit erneuern.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading

from app import config, platforms, resources

log = logging.getLogger(__name__)

DESKTOP_FILE_NAME = config.LINUX_DESKTOP_ID + ".desktop"
MIME_FILE_NAME = config.LINUX_DESKTOP_ID + ".xml"
MIME_ICON_NAME = config.LINUX_MIME_TYPE.replace("/", "-")
ICON_SIZE = "256x256"
TOOL_TIMEOUT_SECONDS = 30
DEFAULTS_SECTION = "[Default Applications]"


def _data_home() -> str:
    return os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")


def _config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def paths(data_home: str | None = None, config_home: str | None = None) -> dict[str, str]:
    """Wohin die Dateien der Zuordnung kommen."""
    data, conf = data_home or _data_home(), config_home or _config_home()
    icons = os.path.join(data, "icons", "hicolor", ICON_SIZE)
    return {
        "desktop": os.path.join(data, "applications", DESKTOP_FILE_NAME),
        "mime": os.path.join(data, "mime", "packages", MIME_FILE_NAME),
        "app_icon": os.path.join(icons, "apps", config.LINUX_DESKTOP_ID + ".png"),
        "mime_icon": os.path.join(icons, "mimetypes", MIME_ICON_NAME + ".png"),
        "mimeapps": os.path.join(conf, "mimeapps.list"),
        "applications": os.path.join(data, "applications"),
        "mime_root": os.path.join(data, "mime"),
    }


def command() -> list[str]:
    """Womit die Verknüpfung das Programm startet: die AppImage-Datei, sonst die Programmdatei bzw. main.py."""
    if resources.is_frozen():
        return [platforms.launch_executable()]
    import sys

    main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "main.py"))
    return [sys.executable, main_script]


RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")
ESCAPED_IN_QUOTES = set('"`$\\')


def exec_argument(argument: str) -> str:
    """Ein Argument für die ``Exec``-Zeile einer ``.desktop``-Datei.

    Nach der freedesktop-Spezifikation: erst die Regeln für ``Exec`` (``%`` verdoppeln, Sonderzeichen in
    Anführungszeichen, darin ``"`$\\`` mit ``\\``), dann die allgemeinen für Zeichenketten (``\\`` verdoppeln).
    """
    argument = argument.replace("%", "%%")
    if any(char in RESERVED for char in argument):
        argument = '"' + "".join("\\" + char if char in ESCAPED_IN_QUOTES else char for char in argument) + '"'
    return argument.replace("\\", "\\\\")


def _value(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def desktop_entry(program: list[str] | None = None, hidden: bool = False) -> str:
    """Inhalt der ``.desktop``-Datei.

    ``hidden``: nur für den Doppelklick auf ``.pap``-Dateien, nicht im Startmenü (``NoDisplay``) – wenn ein
    anderes Werkzeug den Startmenü-Eintrag schon angelegt hat. Dann auch ohne ``TryExec``, damit Werkzeuge wie
    Gear Lever den Eintrag nicht als weiteres Programm auflisten.
    """
    program = program or command()
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_value(config.APP_NAME)}",
        f"Comment={_value(config.file_type_description())}",
        "Exec=" + " ".join(exec_argument(part) for part in program) + " %F",
    ]
    if hidden:
        lines.append("NoDisplay=true")
    elif os.path.isabs(program[0]):
        lines.append(f"TryExec={exec_argument(program[0])}")
    lines += [
        f"Icon={config.LINUX_DESKTOP_ID}",
        "Terminal=false",
        "Categories=Education;Development;",
        f"MimeType={config.LINUX_MIME_TYPE};",
        f"StartupWMClass={os.path.splitext(config.EXECUTABLE_NAME)[0]}",
        f"X-BSTechnik-Version={config.APP_VERSION}",
    ]
    return "\n".join(lines) + "\n"


def mime_definition() -> str:
    """Beschreibung des Dateityps für ``update-mime-database``."""
    from xml.sax.saxutils import escape

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        f'  <mime-type type="{config.LINUX_MIME_TYPE}">\n'
        f'    <comment>{escape(config.file_type_description())}</comment>\n'
        f'    <glob pattern="*{config.FILE_EXTENSION}" weight="80"/>\n'
        f'    <icon name="{MIME_ICON_NAME}"/>\n'
        '  </mime-type>\n'
        '</mime-info>\n')


def _write_if_changed(path: str, content: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == content:
                return False
    except (OSError, UnicodeDecodeError):
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.replace(temp, path)
    return True


def _copy_icon(source_name: str, target: str) -> None:
    source = resources.asset_path(source_name)
    if os.path.isfile(source):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(source, target)


def set_default_application(mimeapps: str, remove: bool = False, desktop_file: str = DESKTOP_FILE_NAME) -> None:
    """Trägt das Programm in ``mimeapps.list`` als Standard für den Dateityp ein (oder entfernt den Eintrag).

    Ändert nur die eine Zeile im Abschnitt ``[Default Applications]``; alles andere bleibt, wie es ist.
    """
    try:
        with open(mimeapps, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        lines = []
    except UnicodeDecodeError as exc:
        raise OSError(str(exc)) from exc
    start = end = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if start is not None and end is None:
                end = index
            if stripped == DEFAULTS_SECTION and start is None:
                start = index
    if start is not None and end is None:
        end = len(lines)
    entry = f"{config.LINUX_MIME_TYPE}={desktop_file};"
    if start is None:
        if remove:
            return
        if lines and lines[-1].strip():
            lines.append("")
        lines += [DEFAULTS_SECTION, entry]
    else:
        kept = [line for line in lines[start + 1:end] if line.split("=", 1)[0].strip() != config.LINUX_MIME_TYPE]
        if not remove:
            kept.insert(0, entry)
        lines[start + 1:end] = kept
    _write_if_changed(mimeapps, "\n".join(lines) + "\n")


def _run_tool(name: str, *arguments: str) -> None:
    """Startet ein Hilfsprogramm des Systems, falls vorhanden (Fehler werden nur protokolliert)."""
    environment = platforms.host_environment()
    tool = shutil.which(name, path=environment.get("PATH"))
    if tool is None:
        log.info("%s ist nicht installiert – übersprungen", name)
        return
    try:
        subprocess.run([tool, *arguments], env=environment, timeout=TOOL_TIMEOUT_SECONDS,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.info("%s fehlgeschlagen: %s", name, exc)


def _refresh(where: dict[str, str]) -> None:
    _run_tool("update-mime-database", where["mime_root"])
    _run_tool("update-desktop-database", where["applications"])


def _desktop_keys(path: str) -> dict[str, str]:
    """Die Schlüssel im Abschnitt ``[Desktop Entry]`` einer ``.desktop``-Datei (ohne Übersetzungen)."""
    keys: dict[str, str] = {}
    section = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith("["):
                    section = line
                elif section == "[Desktop Entry]" and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    keys.setdefault(key.strip(), value.strip())
    except (OSError, UnicodeDecodeError):
        pass
    return keys


def _program_of(keys: dict[str, str]) -> str | None:
    """Die Programmdatei eines Eintrags (aus ``TryExec`` oder dem ersten Teil von ``Exec``)."""
    import shlex

    if keys.get("TryExec"):
        return keys["TryExec"]
    try:
        parts = shlex.split(keys.get("Exec", "").replace("\\\\", "\\"))
    except ValueError:
        return None
    # „env VAR=… programm“ (so schreiben manche Werkzeuge Umgebungsvariablen in den Eintrag)
    while parts and (parts[0] == "env" or ("=" in parts[0] and not parts[0].startswith("/"))):
        parts.pop(0)
    return parts[0] if parts else None


def foreign_entry(program: list[str] | None = None, data_home: str | None = None) -> tuple[str, bool] | None:
    """Ein Startmenü-Eintrag eines anderen Werkzeugs für genau diese AppImage-Datei – z. B. von Gear Lever
    (``~/AppImages/…appimage``) oder AppImageLauncher. ``(Dateiname, kennt den Dateityp .pap)`` oder ``None``."""
    program = program or command()
    target = os.path.realpath(program[0])
    folder = paths(data_home)["applications"]
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        if not name.endswith(".desktop") or name == DESKTOP_FILE_NAME:
            continue
        keys = _desktop_keys(os.path.join(folder, name))
        executable = _program_of(keys)
        if not executable or keys.get("Hidden", "").lower() == "true":
            continue
        if os.path.realpath(os.path.expanduser(executable)) == target:
            return name, config.LINUX_MIME_TYPE in keys.get("MimeType", "").split(";")
    return None


def _plan(program: list[str] | None, data_home: str | None) -> tuple[str | None, str]:
    """Was eingerichtet werden soll: (Inhalt des eigenen Eintrags oder ``None`` = keiner, Standardprogramm).

    Hat ein anderes Werkzeug schon einen Startmenü-Eintrag für diese Datei angelegt, entsteht kein zweiter:
    Kennt er den Dateityp, öffnet er auch die ``.pap``-Dateien; sonst übernimmt das ein unsichtbarer eigener
    Eintrag.
    """
    foreign = foreign_entry(program, data_home)
    if foreign is None:
        return desktop_entry(program), DESKTOP_FILE_NAME
    name, knows_type = foreign
    if knows_type:
        return None, name
    return desktop_entry(program, hidden=True), DESKTOP_FILE_NAME


def register(program: list[str] | None = None, data_home: str | None = None, config_home: str | None = None,
             run_tools: bool = True) -> bool:
    """Richtet Startmenü-Eintrag, Dateityp, Symbole und Standardprogramm ein.

    ``True``, wenn sich etwas geändert hat. Wirft ``OSError`` bei Fehlern.
    """
    where = paths(data_home, config_home)
    entry, default = _plan(program, data_home)
    changed = _write_if_changed(where["mime"], mime_definition())
    if entry is None:
        if os.path.exists(where["desktop"]):
            os.remove(where["desktop"])  # früher selbst angelegt: sonst stünde das Programm doppelt im Startmenü
            changed = True
    else:
        changed = _write_if_changed(where["desktop"], entry) or changed
        try:
            os.chmod(where["desktop"], 0o755)  # manche Dateimanager starten nur „vertrauenswürdige“ Einträge
        except OSError:
            pass
    _copy_icon("app_icon.png", where["app_icon"])
    _copy_icon("file_icon.png", where["mime_icon"])
    set_default_application(where["mimeapps"], desktop_file=default)
    if run_tools:
        _refresh(where)
    return changed


def unregister(data_home: str | None = None, config_home: str | None = None, run_tools: bool = True) -> None:
    where = paths(data_home, config_home)
    for key in ("desktop", "mime", "app_icon", "mime_icon"):
        try:
            os.remove(where[key])
        except FileNotFoundError:
            pass
    set_default_application(where["mimeapps"], remove=True)
    if run_tools:
        _refresh(where)


def needs_installation(program: list[str] | None = None, data_home: str | None = None) -> bool:
    """Fehlt die Verknüpfung oder zeigt sie auf eine andere Programmdatei bzw. Version?"""
    where = paths(data_home)
    entry, _default = _plan(program, data_home)
    try:
        with open(where["desktop"], "r", encoding="utf-8") as handle:
            current = handle.read()
    except FileNotFoundError:
        current = None
    except (OSError, UnicodeDecodeError):
        return True
    return current != entry or not os.path.isfile(where["mime"])


def ensure_installed(background: bool = True) -> bool:
    """Beim Start des AppImage: Verknüpfung und Dateityp einrichten, wenn sie fehlen oder veraltet sind.

    Nur im AppImage (aus dem Quelltext geschieht das nur über das Menü). ``True``, wenn eingerichtet wird.
    """
    if platforms.appimage_path() is None or not needs_installation():
        return False

    def work() -> None:
        try:
            register()
            log.info("Desktop-Verknüpfung und Dateityp „%s“ eingerichtet", config.FILE_EXTENSION)
        except OSError:
            log.exception("Desktop-Verknüpfung konnte nicht eingerichtet werden")

    if background:
        threading.Thread(target=work, name="desktop-integration", daemon=True).start()
    else:
        work()
    return True
