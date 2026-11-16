"""User-facing release notes and guided update tour definitions."""

from typing import Any, Dict


def get_version_changelog(version: str) -> Dict[str, Any]:
    """Returns the structured steps shown to users on first launch after an update."""
    return {
        "version": version,
        "title": f"Novedades de StreamDesk v{version}",
        "steps": [
            {
                "title": "Spotify y juegos sin interferencias",
                "tag": "Estabilidad",
                "icon": "shield",
                "description": (
                    "«Me gusta», aleatorio y repetir de Spotify funcionan en segundo plano, sin robar el foco "
                    "ni enviar teclas mientras juegas a pantalla completa."
                ),
            },
            {
                "title": "Deshacer, rehacer y edición segura en Studio",
                "tag": "Studio",
                "icon": "sliders",
                "description": (
                    "Ctrl+Z y Ctrl+Y recorren tus cambios en orden, pegar sobre una casilla ocupada pide "
                    "confirmación y un guardado rechazado vuelve al último estado válido."
                ),
            },
            {
                "title": "Móvil más claro y conexión más segura",
                "tag": "Móvil",
                "icon": "power",
                "description": (
                    "Cada botón muestra «en curso», éxito o error, avisa si no hay conexión, recuerda la app de "
                    "cada fader y la app de Android rechaza PCs que se hagan pasar por el tuyo."
                ),
            },
        ],
    }
