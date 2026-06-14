"""Ports for the transcript-history slice.

Implemented in infrastructure / the composition root. The reader is the SAME
read-only transcript reader the distill slice uses (ADR-020): files are read,
never written. The catalog resolves which registered agents have transcripts and
where their config dir lives.
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.distill.session import TranscriptSession
from coffer.domain.knowledge.document import Document


class TranscriptReaderPort(Protocol):
    def list_sessions(
        self, *, agent_type_value: str, config_dir: str
    ) -> list[TranscriptSession]: ...

    def read_session(
        self, *, agent_type_value: str, config_dir: str, session_id: str
    ) -> TranscriptSession: ...


class AgentCatalogPort(Protocol):
    async def list_agents(self) -> list[str]: ...  # registered agent names

    async def resolve(self, name: str) -> tuple[str, str]: ...  # (agent_type_value, config_dir)


class DocumentStorePort(Protocol):
    """The subset of the shared ``DocumentRepo`` the history slice uses.

    Declared as a Protocol so the service is typed + fakeable without importing
    the concrete infrastructure repo (mirrors ``MemoryDocumentRepo``).
    """

    async def upsert_document(self, d: Document) -> Document: ...
    async def get_document(self, kind: str, resource_name: str, doc_id: str) -> Document | None: ...
    async def list_documents(
        self, kind: str, resource_name: str, *, limit: int, offset: int
    ) -> list[Document]: ...
    async def delete_document(self, kind: str, resource_name: str, doc_id: str) -> bool: ...
    async def delete_resource(self, kind: str, resource_name: str) -> int: ...
