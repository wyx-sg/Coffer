"""Domain and view shapes onto the /api/v1/sync wire models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, cast

from coffer.application.sync.views import MachineView, StoppedRound, SyncStatus
from coffer.domain.sync.handoffs import is_secret_file
from coffer.domain.sync.joins import JoinPreview
from coffer.domain.sync.plaintext import PlaintextFinding
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import AppliedChange, RoundRecord
from coffer.domain.sync.stops import ConflictFile
from coffer.surfaces.http.handoff_schemas import handoff_out
from coffer.surfaces.http.sync_schemas import (
    AgentInventoryOut,
    AreaCountsOut,
    MachineOut,
    PlaintextFindingOut,
    ProblemOut,
    PulledCommitOut,
    RoundOut,
    SyncChangeOut,
    SyncPluginOut,
    SyncRemoteOut,
    SyncStatusOut,
    WaitingCommitOut,
)
from coffer.surfaces.http.sync_stop_schemas import (
    AreaCountOut,
    BreachOut,
    ConflictFileOut,
    HoldGroupOut,
    HoldOut,
    JoinPreviewOut,
    StoppedRoundOut,
)

_Change = Literal["added", "modified", "removed"]


def change_out(c: AppliedChange) -> SyncChangeOut:
    status = c.status if c.status in ("added", "modified", "removed") else "modified"
    return SyncChangeOut(path=c.path, status=cast(_Change, status))


def round_out(r: RoundRecord) -> RoundOut:
    return RoundOut(
        id=r.id,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        trigger=r.trigger,
        from_commit=r.from_commit,
        to_commit=r.to_commit,
        snapshot=r.snapshot,
        pulled=[
            PulledCommitOut(version=c.version, time=c.time, machine=c.machine, files=c.files)
            for c in r.pulled
        ],
        applied=[change_out(c) for c in r.applied],
        pushed=[change_out(c) for c in r.pushed],
        with_machines=list(r.with_machines),
        conflicts=r.conflicts,
        held=r.held,
        detail=r.detail,
        path=r.path,
        join=r.join,
        pulled_files=r.pulled_files,
        pushed_files=r.pushed_files,
        plaintext=plaintext_out(r.plaintext),
        folded=r.folded,
    )


def plaintext_out(found: Sequence[PlaintextFinding]) -> list[PlaintextFindingOut]:
    return [
        PlaintextFindingOut(path=f.path, line=f.line, key=f.key, current=f.current) for f in found
    ]


def remote_out(remote: SyncRemote) -> SyncRemoteOut:
    return SyncRemoteOut(
        url=remote.url,
        branch=remote.branch,
        secret_ref=remote.secret_ref,
        username=remote.username,
        include_secret=remote.include_secret,
        interval_seconds=remote.interval_seconds,
        enabled=remote.enabled,
    )


def status_out(s: SyncStatus) -> SyncStatusOut:
    problem = s.problem
    return SyncStatusOut(
        configured=s.remote is not None,
        remote=remote_out(s.remote) if s.remote else None,
        machine_id=s.machine_id,
        machine_name=s.machine_name,
        joined=s.joined,
        running_since=s.running_since,
        last_round=round_out(s.last_round) if s.last_round else None,
        next_round_at=s.next_round_at,
        machines=s.machines,
        areas=AreaCountsOut(**vars(s.areas)),
        waiting=[
            WaitingCommitOut(
                version=w.version,
                time=w.time,
                writer=w.writer,
                summary=w.summary,
                changes=[change_out(c) for c in w.changes],
            )
            for w in s.waiting
        ],
        vault_path=s.vault_path,
        synchroniser=s.synchroniser,
        problem=ProblemOut(
            kind=cast(Any, problem.kind),
            message=problem.message,
            secret_ref=problem.secret_ref,
            since=problem.since,
            handoff=handoff_out(problem.handoff),
            plaintext=plaintext_out(problem.plaintext),
        )
        if problem
        else None,
        conflicts=s.conflicts,
        held=s.held,
        join_choices=s.join_choices,
    )


def conflict_out(
    c: ConflictFile, editor_path: str | None = None, *, agent_merge: bool = False
) -> ConflictFileOut:
    return ConflictFileOut(
        path=c.path,
        area=c.area,
        reason=c.reason,
        ours_time=c.ours_time,
        theirs_time=c.theirs_time,
        theirs_machine=c.theirs_machine,
        other_path=c.other_path,
        answer=c.answer,
        editor_path=editor_path,
        secret=is_secret_file(c.path),
        agent_merge=agent_merge,
    )


def stopped_out(s: StoppedRound) -> StoppedRoundOut:
    stop = s.stop
    hold = stop.hold
    return StoppedRoundOut(
        kind=stop.kind.value,
        raised_at=stop.raised_at,
        local=stop.local,
        remote=stop.remote,
        join=stop.join,
        files=[conflict_out(f.file, f.editor_path, agent_merge=f.agent_merge) for f in s.files],
        unanswered=len(stop.unanswered),
        hold=HoldOut(
            direction=hold.direction.value,
            breaches=[BreachOut(area=b.area, lost=b.lost, total=b.total) for b in hold.breaches],
            paths=list(hold.paths),
            groups=[
                HoldGroupOut(folder=g.folder, paths=list(g.paths), total=g.total) for g in s.groups
            ],
            machines=list(s.machines),
            confirmed=s.confirmed,
        )
        if hold
        else None,
        handoff=handoff_out(s.handoff),
    )


def preview_out(p: JoinPreview) -> JoinPreviewOut:
    return JoinPreviewOut(
        kind=p.kind.value,
        remote_tip=p.remote_tip,
        pushed_by=p.pushed_by,
        pushed_at=p.pushed_at,
        pulled=[AreaCountOut(area=a.area, files=a.files) for a in p.pulled],
        same=p.same,
        differ=list(p.differ),
        pushed=[AreaCountOut(area=a.area, files=a.files) for a in p.pushed],
        deleted=list(p.deleted),
        conflicts=list(p.conflicts),
        same_name=list(p.same_name),
        refused=p.refused,
        pulled_files=p.pulled_files,
        pushed_files=p.pushed_files,
    )


def machine_out(v: MachineView) -> MachineOut:
    d = v.descriptor
    return MachineOut(
        machine_id=d.machine_id,
        name=d.name,
        os=d.os,
        hostname=d.hostname,
        coffer_version=d.coffer_version,
        last_round_at=d.last_round_at,
        last_converged_commit=d.last_converged_commit,
        key_fingerprint=d.key_fingerprint,
        key_matches=v.key_matches,
        is_self=v.is_self,
        last_round=v.last_round,
        agents=[
            AgentInventoryOut(
                type=a.type,
                name=a.name,
                plugins=[
                    SyncPluginOut(
                        id=p.id,
                        name=p.name,
                        marketplace=p.marketplace,
                        enabled=p.enabled,
                        version=p.version,
                    )
                    for p in a.plugins
                ],
            )
            for a in d.agents
        ],
    )


__all__ = [
    "change_out",
    "conflict_out",
    "machine_out",
    "preview_out",
    "remote_out",
    "round_out",
    "status_out",
    "stopped_out",
]
