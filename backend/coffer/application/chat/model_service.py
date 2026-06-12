"""ModelService — CRUD + default-invariant management for chat model configs.

The single-default invariant:
- The first model created becomes the default.
- Deleting the default model promotes another remaining model (alphabetically
  by ``created_at`` ascending, i.e. the oldest surviving model) to default.
- If no models remain after a delete, there is no default.
- At most one model has ``is_default=True`` at any time.

``display_name`` must be unique across all model configs; attempting to create
or update to a name already taken raises ``ModelRejected(reason="duplicate_name")``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.chat.model import ModelConfig, ProviderType
from coffer.domain.errors import ModelNotFound, ModelRejected


class ChatModelRepo(Protocol):
    """Persistence port for ``ModelConfig`` rows."""

    async def create(self, model: ModelConfig) -> ModelConfig: ...

    async def get(self, model_id: str) -> ModelConfig | None: ...

    async def list(self) -> list[ModelConfig]: ...

    async def update(self, model: ModelConfig) -> ModelConfig: ...

    async def delete(self, model_id: str) -> None: ...

    async def get_default(self) -> ModelConfig | None: ...

    async def set_default(self, model_id: str) -> None: ...


class ModelService:
    """Application service for model-config lifecycle management."""

    def __init__(
        self,
        *,
        repo: ChatModelRepo,
        audit: AuditService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def get_default(self) -> ModelConfig | None:
        """Return the current default model, or ``None`` if none exists."""
        return await self._repo.get_default()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        display_name: str,
        provider: ProviderType | str,
        model: str,
        credential_ref: str | None,
        base_url: str | None,
        is_default: bool = False,
        actor: str = "user",
    ) -> ModelConfig:
        """Create a new model config.

        The first model created is always the default. A later model created
        with ``is_default=True`` is promoted (demoting the previous default).
        ``ModelConfig.__post_init__`` validates provider-specific fields and
        raises ``ModelRejected`` for invalid input.
        Raises ``ModelRejected(reason="duplicate_name")`` when ``display_name``
        is already taken.
        """
        await self._assert_name_unique(display_name)

        existing = await self._repo.list()
        first_model = len(existing) == 0
        # Persist the row not-yet-default; promotion goes exclusively through
        # set_default() so there is never a window with two defaults.
        now = datetime.now(tz=UTC)
        # ModelConfig.__post_init__ raises ModelRejected for invalid fields.
        new_model = ModelConfig(
            id=uuid.uuid4().hex,
            display_name=display_name,
            provider=ProviderType(provider) if isinstance(provider, str) else provider,
            model=model,
            credential_ref=credential_ref,
            base_url=base_url,
            is_default=first_model,
            created_at=now,
            updated_at=now,
        )
        created = await self._repo.create(new_model)
        # A non-first model explicitly requested as default is promoted now.
        if is_default and not first_model:
            await self._repo.set_default(created.id)
            reloaded = await self._repo.get(created.id)
            created = reloaded if reloaded is not None else created
        await self._audit.record(
            AuditEventType.MODEL_CREATED.value,
            actor=actor,
            details={"model_id": created.id, "display_name": created.display_name},
        )
        return created

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list(self) -> list[ModelConfig]:
        """Return all configured models (no specific order guaranteed)."""
        return await self._repo.list()

    async def get(self, model_id: str) -> ModelConfig:
        """Return a single model config; raises ``ModelNotFound`` if absent."""
        row = await self._repo.get(model_id)
        if row is None:
            raise ModelNotFound(model_id)
        return row

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        model_id: str,
        *,
        display_name: str | None = None,
        provider: ProviderType | str | None = None,
        model: str | None = None,
        credential_ref: str | None = None,
        base_url: str | None = None,
        is_default: bool | None = None,
        actor: str = "user",
    ) -> ModelConfig:
        """Partially update a model config.

        Only supplied (non-``None``) fields are changed.  Setting
        ``is_default=True`` promotes this model and demotes the previous
        default.  Raises ``ModelRejected(reason="duplicate_name")`` when the
        new ``display_name`` is already taken by another model.
        """
        existing = await self.get(model_id)

        new_display_name = display_name if display_name is not None else existing.display_name
        if display_name is not None and display_name != existing.display_name:
            await self._assert_name_unique(display_name)

        new_provider: ProviderType
        if provider is not None:
            new_provider = ProviderType(provider) if isinstance(provider, str) else provider
        else:
            new_provider = existing.provider

        new_model = model if model is not None else existing.model
        new_cred = credential_ref if credential_ref is not None else existing.credential_ref
        new_url = base_url if base_url is not None else existing.base_url
        # Never write is_default via the plain field-update path: doing so would
        # create a window (across the await) where two models are both default.
        # Default promotion is handled exclusively via set_default() below.
        # is_default=False is treated as a no-op to preserve the single-default
        # invariant (you can only change the default by promoting another model).

        now = datetime.now(tz=UTC)
        updated = ModelConfig(
            id=existing.id,
            display_name=new_display_name,
            provider=new_provider,
            model=new_model,
            credential_ref=new_cred,
            base_url=new_url,
            is_default=existing.is_default,  # keep current value; set_default handles changes
            created_at=existing.created_at,
            updated_at=now,
        )
        saved = await self._repo.update(updated)

        # Promote this model to default if requested (atomic: demotes others first).
        if is_default is True:
            await self._repo.set_default(model_id)
            # Reload to reflect the change.
            reloaded = await self._repo.get(model_id)
            saved = reloaded if reloaded is not None else saved

        await self._audit.record(
            AuditEventType.MODEL_UPDATED.value,
            actor=actor,
            details={"model_id": model_id, "display_name": saved.display_name},
        )
        return saved

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, model_id: str, *, actor: str = "user") -> None:
        """Delete a model config.

        If the deleted model was the default, the oldest remaining model (by
        ``created_at``) is promoted.  If no models remain, there is no default.
        Raises ``ModelNotFound`` when the model does not exist.
        """
        existing = await self.get(model_id)
        was_default = existing.is_default

        await self._repo.delete(model_id)

        if was_default:
            remaining = await self._repo.list()
            if remaining:
                # Promote the oldest surviving model.
                oldest = min(remaining, key=lambda m: m.created_at)
                await self._repo.set_default(oldest.id)

        await self._audit.record(
            AuditEventType.MODEL_DELETED.value,
            actor=actor,
            details={"model_id": model_id, "display_name": existing.display_name},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _assert_name_unique(self, display_name: str) -> None:
        """Raise ``ModelRejected`` when ``display_name`` is already in use."""
        all_models = await self._repo.list()
        for m in all_models:
            if m.display_name == display_name:
                raise ModelRejected(
                    reason="duplicate_name",
                    message=f"a model named {display_name!r} already exists",
                )
