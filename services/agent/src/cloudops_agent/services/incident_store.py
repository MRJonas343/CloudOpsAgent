"""In-memory incident store with deterministic sequential IDs."""

from cloudops_agent.models import Incident, IncidentStatus, IncidentType

_TERMINAL_STATUSES = frozenset({IncidentStatus.resolved, IncidentStatus.failed})


class IncidentStore:
    """Stores incidents in memory and assigns stable ``INC-####`` IDs."""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._sequence = 0

    def add(self, incident: Incident) -> Incident:
        """Store ``incident`` under the next sequential ID and return the copy."""
        stored = incident.model_copy(update={"incident_id": self._next_id()})
        self._incidents[stored.incident_id] = stored
        return stored

    def get(self, incident_id: str) -> Incident | None:
        """Return the incident with ``incident_id`` or ``None``."""
        return self._incidents.get(incident_id)

    def set_status(self, incident_id: str, status: IncidentStatus) -> Incident | None:
        """Write ``status`` through to the stored incident.

        Returns the updated incident, or ``None`` when the id is unknown. This is
        the run service's write-through: the run record holds the detail and the
        incident keeps only the lifecycle status that ``find_active`` reads.
        """
        incident = self._incidents.get(incident_id)
        if incident is None:
            return None
        updated = incident.model_copy(update={"status": status})
        self._incidents[incident_id] = updated
        return updated

    def list(self) -> list[Incident]:
        """Return all stored incidents in insertion order."""
        return list(self._incidents.values())

    def find_active(self, service: str, incident_type: IncidentType) -> Incident | None:
        """Return an open incident for ``service``/``incident_type`` if one exists."""
        for incident in self._incidents.values():
            if (
                incident.service == service
                and incident.type == incident_type
                and incident.status not in _TERMINAL_STATUSES
            ):
                return incident
        return None

    def _next_id(self) -> str:
        self._sequence += 1
        return f"INC-{self._sequence:04d}"
