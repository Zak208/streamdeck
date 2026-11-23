"""User-facing release notes and guided update tour definitions."""

from typing import Any, Dict


def get_version_changelog(version: str) -> Dict[str, Any]:
    """Returns the structured steps shown to users on first launch after an update."""
    return {
        "version": version,
        "title": f"Novedades de StreamDesk v{version}",
        "steps": [
            {
                "title": "Navegación multi-página independiente",
                "tag": "Páginas",
                "icon": "sliders",
                "description": (
                    "Los botones de cualquier página (Spotify, Discord, OBS...) responden al instante desde el móvil o la web, "
                    "incluso si el PC se encuentra en una página distinta."
                ),
            },
            {
                "title": "Sistema de logs y diagnóstico de errores",
                "tag": "Diagnóstico",
                "icon": "notes",
                "description": (
                    "Nuevo visor de logs en tiempo real en Studio y en la app móvil. Registro detallado de fallos, "
                    "rotación automática de archivo y herramientas para copiar y descargar el registro."
                ),
            },
            {
                "title": "Resiliencia y estabilidad del sistema",
                "tag": "Estabilidad",
                "icon": "shield",
                "description": (
                    "Sincronización PTT segura en cualquier página, detección robusta de acciones y registro persistente en disco."
                ),
            },
        ],
    }
