"""User-facing release notes and guided update tour definitions."""

from typing import Any, Dict


def get_version_changelog(version: str) -> Dict[str, Any]:
    """Returns the structured steps shown to users on first launch after an update."""
    return {
        "version": version,
        "title": f"Novedades de StreamDesk v{version}",
        "steps": [
            {
                "title": "Blindaje y seguridad integral",
                "tag": "Seguridad",
                "icon": "shield",
                "description": (
                    "Bloqueo estricto de atajos de sistema peligrosos, protección anti-replay y límite de fuerza bruta en PIN, "
                    "cifrado robusto con Windows DPAPI y protección contra SSRF en webhooks."
                ),
            },
            {
                "title": "Control de acceso y privacidad reforzada",
                "tag": "Privacidad",
                "icon": "power",
                "description": (
                    "Validación recursiva de permisos en acciones condicionales para móviles limitados y protección de acceso local "
                    "a StreamDesk Studio en la red Wi-Fi."
                ),
            },
            {
                "title": "Resiliencia y estabilidad del sistema",
                "tag": "Estabilidad",
                "icon": "sliders",
                "description": (
                    "Control de volumen optimizado contra saturación de memoria, validación de estado en Push-to-Talk y sincronización "
                    "segura de hilos COM en segundo plano."
                ),
            },
        ],
    }
