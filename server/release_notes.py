"""User-facing release notes and guided update tour definitions."""

from typing import Any, Dict


def get_version_changelog(version: str) -> Dict[str, Any]:
    """Returns the structured steps shown to users on first launch after an update."""
    return {
        "version": version,
        "title": f"Novedades de StreamDesk v{version}",
        "steps": [
            {
                "title": "Independencia de juegos y aplicaciones activas",
                "tag": "Estabilidad",
                "icon": "shield",
                "description": (
                    "Las acciones como «Me gusta» en Spotify ahora añaden y quitan canciones de forma exacta "
                    "en «Canciones que te gustan» (incluso si están en otras listas) sin interferir ni "
                    "cambiar el foco mientras juegas a Valorant u otras aplicaciones a pantalla completa."
                ),
            },
            {
                "title": "Deshacer, rehacer y edición segura en Studio",
                "tag": "Studio",
                "icon": "sliders",
                "description": (
                    "Historial cronológico completo con Ctrl+Z y Ctrl+Y / Ctrl+Shift+Z, confirmación "
                    "antes de sobrescribir casillas ocupadas al pegar y recuperación limpia ante errores."
                ),
            },
            {
                "title": "Móvil y seguridad de conexión reforzada",
                "tag": "Móvil",
                "icon": "power",
                "description": (
                    "Confirmación visual inmediata de acciones («en curso», éxito y error), aviso de "
                    "falta de conexión al navegar, persistencia de faders y protección contra PCs impostores."
                ),
            },
        ],
    }
