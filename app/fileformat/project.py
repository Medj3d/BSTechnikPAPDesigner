"""Kennungen und Versionierung des ``.pap``-Dateiformats.

Eine ``.pap``-Datei ist XML im Aufbau des PapDesigners (``FRAME`` →
``PROJECT`` → ``DIAGRAMS`` → ``DIAGRAM`` …). Angaben, die der PapDesigner
nicht kennt (freie Positionen, Größen, Anschlüsse, Linienführung, Ansicht),
stehen als Attribute eines eigenen XML-Namensraums an denselben Elementen.
Das Attribut ``VERSION`` dieses Namensraums am Wurzelelement versioniert
die Zusatzangaben. Beim Laden gilt:

* gleiche oder ältere Version → laden
* neuere (unbekannte) Version → sauber ablehnen
* keine Version               → Datei ohne Zusatzangaben (z. B. direkt aus
  dem PapDesigner); die Anordnung wird aus dem Raster der Datei abgeleitet

Für eine zukünftige Version 2 wird ``CURRENT_FORMAT_VERSION`` erhöht; der
Leser in ``serializer.py`` behandelt ältere Versionen dann gezielt.
"""

from __future__ import annotations

from app import config
from app.i18n import tr

CURRENT_FORMAT_VERSION = 1

# Namensraum der Zusatzangaben. Er ist Teil des Dateiformats und darf sich
# nie ändern (auch nicht, wenn das Programm umbenannt wird).
EXTENSION_NAMESPACE = "urn:bstechnik:pap-designer"
EXTENSION_PREFIX = "bst"

# Kopfangaben, an denen der PapDesigner eine Datei als seine eigene erkennt
PAP_FRAME_GUID = "2FB25471-B62C-4EE6-BD43-F819C095ACF8"
PAP_FRAME_FORMAT = "0000"
PAP_APP_VERSION = "2.2.0.8"
PAP_CHECKSUM = "UNSIGNED"
PAP_ELEMENT_FORMAT = "1.00"
PAP_TIME_FORMAT = "%Y.%m.%d %H:%M:%S"


class ProjectFileError(Exception):
    """Fehler beim Lesen/Schreiben einer Projektdatei mit verständlicher Meldung."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details


def check_version(value: str | None) -> bool:
    """Prüft die Version der Zusatzangaben einer Datei.

    Gibt ``True`` zurück, wenn die Datei Zusatzangaben enthält, und ``False``
    für eine Datei ohne Zusatzangaben. Wirft ``ProjectFileError`` bei einer
    ungültigen oder zu neuen Version.
    """
    if value is None:
        return False
    try:
        version = int(str(value).strip())
    except ValueError:
        raise ProjectFileError(tr("Die Dateiformat-Version der Datei ist ungültig.")) from None
    if version < 1:
        raise ProjectFileError(tr("Die Dateiformat-Version der Datei ist ungültig."))
    if version > CURRENT_FORMAT_VERSION:
        raise ProjectFileError(tr(
            "Die Datei wurde mit einer neueren Programmversion erstellt "
            "(Dateiformat-Version {version}).\n\n"
            "Diese Version von {app} unterstützt Dateien bis Version "
            "{supported}. Bitte aktualisieren Sie das Programm.",
            version=version, app=config.APP_NAME, supported=CURRENT_FORMAT_VERSION))
    return True
