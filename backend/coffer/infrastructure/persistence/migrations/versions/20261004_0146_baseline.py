"""baseline: the whole ``runs.db`` schema in one revision

``runs.db`` holds history only (ADR history-is-one-sqlite-file-written-only-by-the-daemon):
the MCP invocation log, the audit log, conversations and their messages, the
channel thread bookkeeping, sync rounds, usage metering, ignored attention
items and the workflow tables. This revision creates all of it on an empty
database. Its id is the head the history ended at, so a database already at
``0146`` is at this baseline and needs nothing.

Every later schema change is a revision of its own whose ``down_revision`` is
this one (or the one before it), with a working ``downgrade()``.

Revision ID: 0146
Revises:
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0146"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The descending key the log listings read newest-first. ``idx_audit_resource_uid``
#: and ``idx_invocations_agent`` are ascending.
_NEWEST_FIRST = sa.text("timestamp DESC")


def upgrade() -> None:
    # The MCP invocation log and the audit log.
    op.create_table(
        "mcp_invocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(), nullable=False),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("capability_type", sa.String(), nullable=False),
        sa.Column("capability_key", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("agent_uid", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_invocations_agent", "mcp_invocations", ["agent_uid", "timestamp"])
    op.create_index("idx_invocations_resource", "mcp_invocations", ["resource_uid", _NEWEST_FIRST])
    op.create_index("idx_invocations_session", "mcp_invocations", ["session_id", _NEWEST_FIRST])
    op.create_index("idx_invocations_time", "mcp_invocations", [_NEWEST_FIRST])
    op.create_index("idx_invocations_trace", "mcp_invocations", ["trace_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("resource_kind", sa.String(), nullable=True),
        sa.Column("resource_name", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("resource_uid", sa.String(), nullable=True),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("turn_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_eventtype", "audit_log", ["event_type", _NEWEST_FIRST])
    op.create_index(
        "idx_audit_resource", "audit_log", ["resource_kind", "resource_name", _NEWEST_FIRST]
    )
    op.create_index("idx_audit_resource_uid", "audit_log", ["resource_uid", "timestamp"])
    op.create_index("idx_audit_time", "audit_log", [_NEWEST_FIRST])
    op.create_index("idx_audit_trace", "audit_log", ["trace_id"])

    # Conversations, their messages and the files a reply changed.
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("archived_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("agent_config", sa.Text(), nullable=True),
        sa.Column("channel_uid", sa.String(), nullable=True),
        sa.Column("peer_chat_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversations_archived", "conversations", ["archived_at"])
    op.create_index("idx_conversations_updated", "conversations", ["updated_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'complete'"), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_chat_messages_conv_seq"),
    )
    op.create_index("idx_chat_messages_conv", "chat_messages", ["conversation_id", "seq"])

    op.create_table(
        "chat_reply_files",
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("diff_omitted", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("message_id", "path"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_chat_reply_files_message", "chat_reply_files", ["message_id", "seq"])

    # Channel thread bookkeeping.
    op.create_table(
        "channel_thread_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("active_conversation_id", sa.String(), nullable=True),
        sa.Column("preferred_agent", sa.String(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("parallel_ordinal", sa.Integer(), nullable=True),
        sa.Column("parallel_title", sa.Text(), nullable=True),
        sa.Column("chat_kind", sa.String(), nullable=True),
        sa.Column("preferred_model", sa.String(), nullable=True),
        sa.Column("preferred_effort", sa.String(), nullable=True),
        sa.Column("preferred_cwd", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resource_uid",
            "chat_id",
            "thread_id",
            name="uq_channel_thread_conv_resource_chat_thread",
        ),
    )
    op.create_index(
        "idx_channel_thread_conv_resource", "channel_thread_conversations", ["resource_uid"]
    )

    op.create_table(
        "channel_thread_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("chat_kind", sa.String(), nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_channel_thread_history_conversation"),
    )
    op.create_index(
        "idx_channel_thread_history_thread",
        "channel_thread_history",
        ["resource_uid", "chat_id", "thread_id"],
    )

    op.create_table(
        "channel_outbox",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("chat_kind", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("delivered_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_channel_outbox_conversation", "channel_outbox", ["conversation_id"])
    op.create_index(
        "idx_channel_outbox_pending", "channel_outbox", ["resource_uid", "delivered_at"]
    )

    op.create_table(
        "channel_replies",
        sa.Column("reply_id", sa.String(), nullable=False),
        sa.Column("resource_uid", sa.String(), nullable=False),
        sa.Column("chat_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), server_default=sa.text("''"), nullable=False),
        sa.Column("chat_kind", sa.String(), nullable=False),
        sa.Column("message_ids", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("reply_id"),
    )
    op.create_index(
        "idx_channel_replies_chat", "channel_replies", ["resource_uid", "chat_id", "sent_at"]
    )

    # Sync rounds, usage metering and ignored attention items.
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("join_kind", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_runs_finished_at", "sync_runs", ["finished_at"])

    op.create_table(
        "usage_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("agent_uid", sa.String(), nullable=True),
        sa.Column("agent_type", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("request_class", sa.String(), nullable=True),
        sa.Column("connection_uid", sa.String(), nullable=True),
        sa.Column("member", sa.String(), nullable=True),
        sa.Column("wire", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("stream", sa.Boolean(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("failed_over", sa.Boolean(), nullable=False),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("usage_known", sa.Boolean(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_5m_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_1h_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("web_search_requests", sa.Integer(), nullable=True),
        sa.Column("speed", sa.String(), nullable=True),
        sa.Column("inference_geo", sa.String(), nullable=True),
        sa.Column("upstream_request_id", sa.String(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("price_version", sa.String(), nullable=True),
        sa.Column("unpriced", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "dedupe_key", name="uq_usage_requests_source_dedupe"),
    )
    op.create_index("idx_usage_requests_started", "usage_requests", ["started_at"])

    op.create_table(
        "usage_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(), nullable=False),
        sa.Column("agent_uid", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(), nullable=False),
        sa.Column("connection_uid", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("unknown_requests", sa.Integer(), nullable=False),
        sa.Column("unpriced_requests", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_5m_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_1h_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("web_search_requests", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day",
            "agent_uid",
            "agent_type",
            "connection_uid",
            "model",
            name="uq_usage_daily_group",
        ),
    )

    op.create_table(
        "attention_ignores",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("ignored_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    # Workflow runs.
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("template_ref", sa.String(), nullable=True),
        sa.Column("template_snapshot", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("workdir", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_stage_key", sa.String(), nullable=True),
        sa.Column("current_node_key", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("'1'"), nullable=False),
        sa.Column("tokens_spent", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("inputs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("idx_workflow_runs_updated", "workflow_runs", ["updated_at"])

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("actor", sa.JSON(), nullable=False),
        sa.Column("stage_key", sa.String(), nullable=True),
        sa.Column("node_key", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_workflow_events_run_sequence"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_workflow_events_run", "workflow_events", ["run_id", "sequence"])

    op.create_table(
        "workflow_node_attempts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("stage_key", sa.String(), nullable=False),
        sa.Column("node_key", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("tokens", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("agent", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("effort", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "node_key", "attempt", name="uq_workflow_attempts_run_node_attempt"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_workflow_attempts_run", "workflow_node_attempts", ["run_id"])

    op.create_table(
        "workflow_approvals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("attempt_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_surface", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("decided_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["workflow_node_attempts.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_workflow_approvals_run", "workflow_approvals", ["run_id", "status"])


def downgrade() -> None:
    """Drop every table this revision made (all but Alembic's own), children
    before the tables they reference; their indexes go with them."""
    bind = op.get_bind()
    tables = sa.MetaData()
    tables.reflect(bind)
    tables.remove(tables.tables["alembic_version"])
    tables.drop_all(bind)
