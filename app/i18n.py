"""Mehrsprachigkeit der Oberfläche.

Die Texte im Quelltext sind **deutsch** und zugleich der Schlüssel der Übersetzung::

    tr("Datei speichern")                          # einfacher Text
    tr("{n} Bausteine", n=len(items))              # mit Platzhaltern (``str.format``)
    tr("Ende", ctx="Baustein")                     # gleiches Wort, andere Bedeutung → eigene Übersetzung
    N_("Vorgang")                                  # nur markieren (Tabellen, Konstanten); später tr(variable)

Die Übersetzungen stehen in ``assets/translations/<Sprache>.json`` (ein Objekt ``{"deutscher Text": "Übersetzung"}``).
Deutsch braucht keine Datei: dort gilt der Quelltext selbst. Fehlt ein Eintrag, erscheint der deutsche Text –
nie ein Fehler. Stimmen die Platzhalter einer Übersetzung nicht, wird ebenfalls der deutsche Text verwendet.

Was nicht übersetzt wird: Meldungen für das Fehlerprotokoll, Dateiformat und Schlüsselwörter, die das Programm
selbst auswertet (Bausteintypen, Dateiendungen, die Wörter, an denen die Auswertung der Plantexte hängt).
Texte, die in einer Projektdatei landen (Standardtext eines neuen Bausteins, „ja“/„nein“ an einer Verzweigung),
erkennt das Programm in **allen** Sprachen wieder, siehe ``all_translations``.

Welche Texte es gibt, liest ``tools/extract_strings.py`` aus dem Quelltext (jeder ``tr``-/``N_``-Aufruf mit einem
Textliteral). ``tests/test_i18n.py`` stellt sicher, dass jede Sprache jeden Text vollständig und mit gleichen
Platzhaltern übersetzt.
"""

from __future__ import annotations

import json
import logging
import os
import string
import sys
import threading

from app import resources

log = logging.getLogger(__name__)

SOURCE_LANGUAGE = "de"
PSEUDO_LANGUAGE = "xx"  # nur für Tests: macht jeden Text kenntlich und deckt Abhängigkeiten vom deutschen Wortlaut auf
FALLBACK_LANGUAGE = "en"  # für Systemsprachen, die das Programm nicht kennt

# Sprachcode → Name in der Sprache selbst (so erkennt ihn jeder im Menü)
LANGUAGES: dict[str, str] = {
    "de": "Deutsch",
    "en": "English",
    "fr": "Français",
    "es": "Español",
    "pt": "Português (Brasil)",
    "ru": "Русский",
    "ar": "العربية",
    "zh": "中文（简体）",
    "ja": "日本語",
}
RTL_LANGUAGES = frozenset({"ar"})  # Schreibrichtung von rechts nach links
AUTOMATIC = "auto"  # Einstellung „Systemsprache verwenden“

# Qt-Gebietsschema je Sprache (Zahlen-/Datumsformate, Monatsnamen)
QT_LOCALE = {"de": "de_DE", "en": "en_US", "fr": "fr_FR", "es": "es_ES", "pt": "pt_BR", "ru": "ru_RU",
             "ar": "ar", "zh": "zh_CN", "ja": "ja_JP"}
# Dateiname der von Qt mitgelieferten Übersetzung für Standardtexte (Ja/Nein, Kopieren/Einfügen, Druckdialog, …)
QT_TRANSLATION = {"de": "de", "fr": "fr", "es": "es", "pt": "pt_BR", "ru": "ru", "ar": "ar", "zh": "zh_CN",
                  "ja": "ja"}
# Schriften für Zeichen, die die Standardschrift nicht hat (Reihenfolge = Vorrang; Chinesisch und Japanisch
# teilen sich viele Zeichen, die je nach Schrift unterschiedlich aussehen)
FONT_FALLBACKS = {
    "zh": ["Microsoft YaHei UI", "Microsoft JhengHei UI", "Yu Gothic UI", "Meiryo UI", "Malgun Gothic"],
    "ja": ["Yu Gothic UI", "Meiryo UI", "Microsoft YaHei UI", "Microsoft JhengHei UI", "Malgun Gothic"],
}
FONT_FALLBACKS_DEFAULT = ["Microsoft YaHei UI", "Yu Gothic UI", "Meiryo UI", "Malgun Gothic", "Segoe UI Symbol"]

GERMAN_MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                 "November", "Dezember"]

CONTEXT_SEPARATOR = "::"

_language = SOURCE_LANGUAGE
_catalog: dict[str, str] = {}
_catalogs: dict[str, dict[str, str]] = {}
_lock = threading.RLock()
_qt_translators: list = []


# ------------------------------------------------------------------ Kataloge
def translations_directory() -> str:
    return resources.asset_path("translations")


def load_catalog(code: str) -> dict[str, str]:
    """Der Katalog einer Sprache (leer für Deutsch oder wenn die Datei fehlt)."""
    if code == SOURCE_LANGUAGE:
        return {}
    with _lock:
        if code not in _catalogs:
            path = os.path.join(translations_directory(), f"{code}.json")
            data: dict = {}
            try:
                with open(path, encoding="utf-8-sig") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    data = {k: v for k, v in loaded.items() if isinstance(k, str) and isinstance(v, str) and v}
            except FileNotFoundError:
                log.info("Keine Übersetzung für „%s“ gefunden: %s", code, path)
            except (OSError, ValueError):
                log.warning("Die Übersetzung für „%s“ ist unlesbar: %s", code, path)
            _catalogs[code] = data
        return _catalogs[code]


def available_languages() -> list[str]:
    """Die Sprachen, die zur Auswahl stehen: Deutsch und jede mit vorhandener Übersetzung."""
    return [code for code in LANGUAGES if code == SOURCE_LANGUAGE or load_catalog(code)]


def placeholders(text: str) -> list[str]:
    """Die Platzhalter eines Textes (``{name}``), sortiert und ohne Doppelte."""
    names = set()
    try:
        for _literal, field, _spec, _conversion in string.Formatter().parse(text):
            if field is not None:
                names.add(field)
    except ValueError:
        return ["<ungültig>"]
    return sorted(names)


def all_translations(text: str, ctx: str | None = None) -> set[str]:
    """Der Text in **allen** Sprachen (deutsch eingeschlossen).

    Für Texte, die in einer Projektdatei landen und später in jeder Sprache wiedererkannt werden müssen,
    z. B. der Standardtext eines Bausteins.
    """
    key = _key(text, ctx)
    found = {text}
    for code in LANGUAGES:
        translated = load_catalog(code).get(key) or load_catalog(code).get(text)
        if translated:
            found.add(translated)
    if _language == PSEUDO_LANGUAGE:
        found.add(_pseudo(text))  # die Testsprache verhält sich wie eine echte Sprache
    return found


# ------------------------------------------------------------ Sprache wählen
def normalize(code: str | None) -> str:
    """„de-DE“, „PT_br“, „zh-Hans“ → Sprachcode aus ``LANGUAGES`` (sonst ``""``)."""
    if not code:
        return ""
    base = str(code).replace("_", "-").split("-")[0].lower()
    return base if base in LANGUAGES else ""


def system_language() -> str:
    """Die Sprache des Systems – oder Englisch, wenn das Programm sie nicht kennt."""
    from PySide6.QtCore import QLocale

    try:
        candidates = list(QLocale.system().uiLanguages()) + [QLocale.system().name()]
    except Exception:  # pragma: no cover - Absicherung
        candidates = []
    for candidate in candidates:
        code = normalize(candidate)
        if code:
            return code
    return FALLBACK_LANGUAGE


def resolve(preference: str | None) -> str:
    """Die einzustellende Sprache für eine gespeicherte Auswahl (``auto`` oder ein Sprachcode).

    Eine Sprache ohne Übersetzungsdatei fällt auf Englisch (bzw. Deutsch) zurück.
    """
    code = normalize(preference) if preference and preference != AUTOMATIC else system_language()
    code = code or FALLBACK_LANGUAGE
    if code == SOURCE_LANGUAGE or load_catalog(code):
        return code
    return FALLBACK_LANGUAGE if load_catalog(FALLBACK_LANGUAGE) else SOURCE_LANGUAGE


def set_language(code: str) -> str:
    """Stellt die Sprache für ``tr`` ein und liefert den tatsächlich verwendeten Code."""
    global _language, _catalog
    with _lock:
        if code == PSEUDO_LANGUAGE:
            _language, _catalog = PSEUDO_LANGUAGE, {}
            return _language
        code = normalize(code) or SOURCE_LANGUAGE
        _language, _catalog = code, load_catalog(code)
        return _language


def language() -> str:
    return _language


def is_rtl(code: str | None = None) -> bool:
    return (code or _language) in RTL_LANGUAGES


def language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


# ------------------------------------------------------------ Übersetzen
def _key(text: str, ctx: str | None) -> str:
    return f"{ctx}{CONTEXT_SEPARATOR}{text}" if ctx else text


def _pseudo(text: str) -> str:
    """Kenntlich gemachter Text: Platzhalter bleiben unverändert, alles andere wird eingerahmt."""
    return f"⟦{text}⟧"


def _lookup(text: str, ctx: str | None) -> str:
    if _language == PSEUDO_LANGUAGE:
        return _pseudo(text)
    if not _catalog:
        return text
    if ctx:
        found = _catalog.get(_key(text, ctx))
        if found:
            return found
    return _catalog.get(text) or text


def _fill(translated: str, source: str, values: dict) -> str:
    if not values:
        return translated
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        log.warning("Platzhalter der Übersetzung passen nicht zum Text: %r", source)
        return source.format(**values)


def tr(text: str, /, *, ctx: str | None = None, **values) -> str:
    """Übersetzt einen (deutschen) Text in die eingestellte Sprache; ``values`` füllen die Platzhalter.

    Der Text wird nur der Position nach übergeben – so darf auch ein Platzhalter ``{text}`` heißen.
    """
    return _fill(_lookup(text, ctx), text, values)


def N_(text: str, /, *, ctx: str | None = None) -> str:
    """Markiert einen Text zum Übersetzen, ohne ihn zu übersetzen (für Tabellen und Konstanten).

    Angezeigt wird er später mit ``tr(variable)``.
    """
    return text


def tr_code(text: str, /, *, ctx: str | None = None, **values) -> str:
    """Wie ``tr``, aber für erzeugten Programmtext (Pseudocode, Kommentare in Python/Java): Deutsch bleibt
    Deutsch, jede andere Oberflächensprache erzeugt englischen Programmtext."""
    if _language in (SOURCE_LANGUAGE, PSEUDO_LANGUAGE):
        return tr(text, ctx=ctx, **values)
    found = load_catalog(FALLBACK_LANGUAGE).get(_key(text, ctx)) or load_catalog(FALLBACK_LANGUAGE).get(text) or text
    return _fill(found, text, values)


def release_date_text(release: str | None = None) -> str:
    """„Oktober 2026“ (wie in ``config.APP_RELEASE_DATE``) mit dem Monatsnamen der eingestellten Sprache."""
    from app import config

    release = release or config.APP_RELEASE_DATE
    parts = release.split()
    if len(parts) == 2 and parts[0] in GERMAN_MONTHS and parts[1].isdigit():
        month = GERMAN_MONTHS.index(parts[0]) + 1
        if _language in (SOURCE_LANGUAGE, PSEUDO_LANGUAGE):
            return release
        from PySide6.QtCore import QLocale

        name = QLocale(QT_LOCALE.get(_language, "en_US")).standaloneMonthName(month, QLocale.FormatType.LongFormat)
        return f"{name} {parts[1]}" if name else release
    return release


# ------------------------------------------------------- Schrift und Qt-Anbindung
def font_fallbacks(code: str | None = None) -> list[str]:
    """Schriften für Zeichen (Chinesisch, Japanisch, …), die die Standardschrift nicht enthält."""
    return list(FONT_FALLBACKS.get(code or _language, FONT_FALLBACKS_DEFAULT))


def _qt_translation_directories() -> list[str]:
    from PySide6.QtCore import QLibraryInfo

    candidates = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
    try:
        import PySide6

        candidates.append(os.path.join(os.path.dirname(PySide6.__file__), "translations"))
    except ImportError:  # pragma: no cover
        pass
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), "PySide6", "translations"))
    return [path for path in candidates if path and os.path.isdir(path)]


def install_qt_translations(app, code: str) -> bool:
    """Lädt Qts eigene Übersetzung (Standardtexte wie „Ja“/„Nein“, Kopieren/Einfügen, Druckdialog)."""
    from PySide6.QtCore import QTranslator

    for translator in _qt_translators:
        app.removeTranslator(translator)
    _qt_translators.clear()
    name = QT_TRANSLATION.get(code)
    if not name:
        return False
    for directory in _qt_translation_directories():
        translator = QTranslator(app)
        if translator.load(f"qtbase_{name}", directory):
            app.installTranslator(translator)
            _qt_translators.append(translator)
            return True
    return False


def apply_to_application(app, code: str) -> None:
    """Überträgt die Sprache auf Qt: Gebietsschema, Standardtexte, Schreibrichtung, Schriften."""
    from PySide6.QtCore import QLocale, Qt

    from app import config

    QLocale.setDefault(QLocale(QT_LOCALE.get(code, "en_US")))
    install_qt_translations(app, code)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl(code) else Qt.LayoutDirection.LeftToRight)
    base = [f for f in config.ITEM_FONT_FAMILIES if f not in set(FONT_FALLBACKS_DEFAULT)
            and f not in {f for fallback in FONT_FALLBACKS.values() for f in fallback}]
    config.ITEM_FONT_FAMILIES[:] = base + font_fallbacks(code)
