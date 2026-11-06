"""The workflow's own state: observations, per-ticket progress, the write ledger and locks.

One SQLite file in the workflow project. Every agent that runs the skill uses the
same file through the CLI, so a run that crashes leaves enough behind for the
next run, by any agent, to carry on safely.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .contracts import stable_key

VERSION = 2
LOCK_SECONDS = 1800
OPEN = ('started', 'unknown')
ENDED = ('done', 'failed')
# A first sighting of these states is worth a look even with nothing to compare against.
TERMINAL_ON_FIRST_SIGHT = {'dw': {'completed', 'failed', 'pending', 'cancel'},
                           'gitlab_pipeline': {'success', 'failed', 'canceled', 'cancelled', 'skipped'},
                           'gitlab_mr': {'merged', 'closed'}}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS tickets(ticket TEXT PRIMARY KEY,snapshot_json TEXT NOT NULL,checkpoint_json TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(event_key TEXT PRIMARY KEY,ticket TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS progress(ticket TEXT PRIMARY KEY,stage TEXT NOT NULL,next TEXT NOT NULL,next_check_at TEXT,note TEXT NOT NULL,by_owner TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(action_key TEXT PRIMARY KEY,ticket TEXT NOT NULL,kind TEXT NOT NULL,target TEXT NOT NULL,version TEXT NOT NULL,attempt INTEGER NOT NULL,intent_json TEXT NOT NULL,status TEXT NOT NULL,owner TEXT NOT NULL,evidence_json TEXT NOT NULL,reason TEXT NOT NULL,started_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locks(resource TEXT PRIMARY KEY,owner TEXT NOT NULL,generation INTEGER NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''


def iso(now):
    return now.isoformat()


def parse(value):
    return datetime.fromisoformat(value)


class Refused(Exception):
    """A step the state does not allow; the message is the reason code."""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA busy_timeout=15000')
        try:
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version in (0, 1):
                self._upgrade(version)
            elif version != VERSION:
                raise ValueError('unsupported_database_version')
        except BaseException:
            self.db.close()
            raise

    def _upgrade(self, version):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # The prototype's actions/leases/observers tables belonged to its Codex launcher.
            for old in ('actions', 'leases', 'observers'):
                if old in tables:
                    if self.db.execute('SELECT count(*) FROM ' + old).fetchone()[0]:
                        raise ValueError('prototype_' + old + '_not_empty_reconcile_first')
                    self.db.execute('DROP TABLE ' + old)
            for statement in [s for s in SCHEMA.split(';') if s.strip()]:
                self.db.execute(statement)
            self.db.execute('PRAGMA user_version=%d' % VERSION)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def __enter__(self): return self
    def __exit__(self, *args): self.db.close()

    def tx(self):
        store = self

        class _Tx:
            def __enter__(self):
                store.db.execute('BEGIN IMMEDIATE')

            def __exit__(self, kind, *rest):
                store.db.execute('ROLLBACK' if kind else 'COMMIT')
        return _Tx()

    # ---- meta ----
    def meta(self, key, default=None):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        self.db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, json.dumps(value)))

    # ---- observations ----
    def observe(self, fact, now):
        """Save a source fact; return a new pending event when it changed. Same version twice is one event."""
        with self.tx():
            row = self.db.execute('SELECT checkpoint_json FROM tickets WHERE ticket=?', (fact['ticket'],)).fetchone()
            seen = json.loads(row[0]) if row else {}
            ref = fact['source'] + ':' + str(fact['object_id'])
            previous = seen.get(ref)
            seen[ref] = fact
            snapshot = fact if fact['source'] == 'jira' or not row else self.snapshot(fact['ticket'])
            self.db.execute('INSERT INTO tickets VALUES(?,?,?,?) ON CONFLICT(ticket) DO UPDATE SET snapshot_json=excluded.snapshot_json,'
                            'checkpoint_json=excluded.checkpoint_json,updated_at=excluded.updated_at',
                            (fact['ticket'], json.dumps(snapshot), json.dumps(seen), iso(now)))
            if previous and previous['object_version'] == fact['object_version']: return None
            if not previous and fact['source'] != 'jira' and fact['status'] not in TERMINAL_ON_FIRST_SIGHT.get(fact['source'], set()):
                return None
            key = stable_key({k: fact[k] for k in ('ticket', 'source', 'object_id', 'object_version')})
            event = {'event_key': key, 'ticket': fact['ticket'], 'evidence_refs': fact['evidence_refs'], 'fact': fact, 'previous': previous}
            created = self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',
                                      (key, fact['ticket'], json.dumps(event), 'pending', iso(now))).rowcount
            return event if created else None

    def pending_events(self, ticket=None):
        rows = self.db.execute("SELECT payload_json FROM events WHERE status='pending'" + (' AND ticket=?' if ticket else '') +
                               ' ORDER BY updated_at,event_key', (ticket,) if ticket else ())
        return [json.loads(r[0]) for r in rows]

    def snapshot(self, ticket):
        row = self.db.execute('SELECT snapshot_json FROM tickets WHERE ticket=?', (ticket,)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- locks ----
    def lock(self, resource):
        row = self.db.execute('SELECT * FROM locks WHERE resource=?', (resource,)).fetchone()
        return dict(row) if row else None

    def holds(self, resource, owner, now):
        row = self.lock(resource)
        return bool(row and row['owner'] == owner and parse(row['expires_at']) > now)

    def claim(self, resource, owner, now):
        """acquired | renewed | busy | reconcile_first. An expired lock passes on only when its holder left no unconfirmed write."""
        with self.tx():
            row = self.lock(resource)
            expires = iso(now + timedelta(seconds=LOCK_SECONDS))
            if not row:
                self.db.execute('INSERT INTO locks VALUES(?,?,?,?)', (resource, owner, 1, expires))
                return {'status': 'acquired', 'resource': resource, 'generation': 1}
            if row['owner'] == owner:
                self.db.execute('UPDATE locks SET expires_at=? WHERE resource=?', (expires, resource))
                return {'status': 'renewed', 'resource': resource, 'generation': row['generation']}
            if parse(row['expires_at']) > now:
                return {'status': 'busy', 'resource': resource, 'owner': row['owner'], 'expires_at': row['expires_at']}
            left = self.open_actions(owner=row['owner'])
            if left:
                return {'status': 'reconcile_first', 'resource': resource, 'previous_owner': row['owner'],
                        'open_actions': [a['action_key'] for a in left]}
            self.db.execute('UPDATE locks SET owner=?,generation=generation+1,expires_at=? WHERE resource=?', (owner, expires, resource))
            return {'status': 'acquired', 'resource': resource, 'generation': row['generation'] + 1, 'took_over_from': row['owner']}

    def renew(self, owner, now):
        self.db.execute('UPDATE locks SET expires_at=? WHERE owner=? AND expires_at>?',
                        (iso(now + timedelta(seconds=LOCK_SECONDS)), owner, iso(now)))

    def release(self, resource, owner):
        with self.tx():
            row = self.lock(resource)
            if not row or row['owner'] != owner: return {'status': 'not_held', 'resource': resource}
            if self.open_actions(owner=owner):
                return {'status': 'kept', 'resource': resource, 'reason': 'unconfirmed_writes'}
            self.db.execute('DELETE FROM locks WHERE resource=?', (resource,))
            return {'status': 'released', 'resource': resource}

    # ---- write ledger ----
    def open_actions(self, ticket=None, owner=None):
        sql = 'SELECT * FROM ledger WHERE status IN (?,?)'; args = list(OPEN)
        if ticket: sql += ' AND ticket=?'; args.append(ticket)
        if owner: sql += ' AND owner=?'; args.append(owner)
        return [self._action(r) for r in self.db.execute(sql + ' ORDER BY started_at', args)]

    def action(self, key):
        row = self.db.execute('SELECT * FROM ledger WHERE action_key=?', (key,)).fetchone()
        return self._action(row) if row else None

    @staticmethod
    def _action(row):
        a = dict(row)
        a['intent'] = json.loads(a.pop('intent_json')); a['evidence'] = json.loads(a.pop('evidence_json'))
        return a

    def begin(self, owner, ticket, kind, target, version, intent, retry, now):
        """Record a write before it is made. Returns the new action, or what already exists for the same write."""
        with self.tx():
            if not self.holds('ticket:' + ticket, owner, now): raise Refused('ticket_not_claimed')
            others = [a for a in self.open_actions(ticket=ticket)]
            if others: raise Refused('reconcile_first:' + ','.join(a['action_key'] for a in others))
            same = self.db.execute('SELECT * FROM ledger WHERE ticket=? AND kind=? AND target=? AND version=? ORDER BY attempt DESC LIMIT 1',
                                   (ticket, kind, target, version)).fetchone()
            attempt = 1
            if same:
                same = self._action(same)
                if same['status'] == 'done': return {'status': 'already_done', 'action': same}
                if not retry: return {'status': 'failed_before', 'action': same}
                attempt = same['attempt'] + 1
            key = stable_key({'ticket': ticket, 'kind': kind, 'target': target, 'version': version, 'attempt': attempt})
            self.db.execute('INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key, ticket, kind, target, version, attempt, json.dumps(intent), 'started', owner, '[]', '', iso(now), iso(now)))
            self.renew(owner, now)
            return {'status': 'started', 'action': self.action(key)}

    def end(self, key, owner, status, evidence, reason, now):
        """Record what a write actually did. Someone else's write may be closed only once its holder's lock is gone."""
        if status not in ENDED + ('unknown',): raise Refused('invalid_status')
        if not isinstance(evidence, list) or any(not isinstance(e, str) or not e.strip() for e in evidence): raise Refused('invalid_evidence')
        if status == 'done' and not evidence: raise Refused('done_needs_readback_evidence')
        if status != 'done' and not (reason or '').strip(): raise Refused('reason_required')
        with self.tx():
            action = self.action(key)
            if not action: raise Refused('unknown_action')
            if action['status'] not in OPEN: raise Refused('already_ended')
            mine = action['owner'] == owner and self.holds('ticket:' + action['ticket'], owner, now)
            if not mine:
                if self.holds('ticket:' + action['ticket'], action['owner'], now): raise Refused('held_by_its_owner')
                if status == 'unknown': raise Refused('reconcile_needs_an_outcome')
            self.db.execute('UPDATE ledger SET status=?,evidence_json=?,reason=?,updated_at=? WHERE action_key=?',
                            (status, json.dumps(evidence), reason or '', iso(now), key))
            if mine: self.renew(owner, now)
            return {'status': status, 'action': self.action(key), 'reconciled_for': None if mine else action['owner']}

    # ---- progress ----
    def progress(self, ticket):
        row = self.db.execute('SELECT * FROM progress WHERE ticket=?', (ticket,)).fetchone()
        return dict(row) if row else None

    def checkpoint(self, ticket, owner, stage, next_step, next_check_at, note, now):
        """What the ticket is waiting on and what comes next; also marks its current events as looked at."""
        with self.tx():
            if not self.holds('ticket:' + ticket, owner, now): raise Refused('ticket_not_claimed')
            if next_check_at:
                when = parse(next_check_at)
                if when.tzinfo is None: raise Refused('next_check_at_needs_timezone')
                next_check_at = iso(when.astimezone(timezone.utc))
            self.db.execute('INSERT INTO progress VALUES(?,?,?,?,?,?,?) ON CONFLICT(ticket) DO UPDATE SET stage=excluded.stage,next=excluded.next,'
                            'next_check_at=excluded.next_check_at,note=excluded.note,by_owner=excluded.by_owner,updated_at=excluded.updated_at',
                            (ticket, stage, next_step, next_check_at, note, owner, iso(now)))
            handled = self.db.execute("UPDATE events SET status='handled',updated_at=? WHERE ticket=? AND status='pending'",
                                      (iso(now), ticket)).rowcount
            self.renew(owner, now)
            return {'status': 'saved', 'progress': self.progress(ticket), 'events_handled': handled}

    def due(self, now):
        return [dict(r) for r in self.db.execute('SELECT * FROM progress WHERE next_check_at IS NOT NULL AND next_check_at<=?', (iso(now),))]
