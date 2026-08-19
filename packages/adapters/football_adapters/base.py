"""DataSourceAdapter — the free -> paid swap seam."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from football_core.model import Capabilities, Provenance


@runtime_checkable
class DataSourceAdapter(Protocol):
    """Every data source (free or licensed) implements this interface.

    Adapters return *raw provider-shaped* payloads plus canonical
    Capabilities/Provenance; the pipeline normalizes into the canonical model.
    """

    source_key: str

    def list_matches(self) -> list[dict[str, Any]]: ...

    def load_events(self, match_id: str) -> Any: ...

    def load_freeze_frames(self, match_id: str) -> Any: ...

    def capabilities(self, match_id: str) -> Capabilities: ...

    def provenance(self, match_id: str) -> Provenance: ...


class NotEntitledError(RuntimeError):
    """Raised by paid-feed stubs until a commercial licence is configured."""
