#!/usr/bin/env python3
"""Delivery follow-up, one step per call. Any agent (or a person) runs it; it starts no agent and keeps no clock.

Every call prints one JSON object. Exit code 0 = answered (including refusals),
2 = the call itself was invalid or a source could not be read safely.
"""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from follow_delivery_core.calendar import local_now, window  # noqa: E402
from follow_delivery_core.contracts import (eligible_issue, event_allowed, stable_key, upgrade_config,  # noqa: E402
                                            validate_config, validate_observer)
from follow_delivery_core.state import Refused, Store  # noqa: E402

CONFIG = 'config/followup.json'
DB = 'state/followup.sqlite3'


def now_utc():
    return datetime.now(timezone.utc)


def read_config(project):
    return validate_config(json.loads((project / CONFIG).read_text()))


def read_calendar(project, config):
    return json.loads((project / config['calendar_file']).resolve().read_text())['years']


def real_readers(project):
    from follow_delivery_core import readers
    tmp = project / 'state/tmp'
    return {'jira': readers.read_jira, 'object': lambda obj, ticket: readers.read_object(obj, ticket, tmp)}


def compact(event):
    fact = event['fact']
    return {'event_key': event['event_key'], 'source': fact['source'], 'object_id': fact['object_id'], 'status': fact['status'],
            'was': (event.get('previous') or {}).get('status'), 'evidence_refs': event['evidence_refs']}


def tick(project, now, readers):
    """The cheap first call of every run: is there anything to do right now?"""
    config = read_config(project)
    reason = window(now, read_calendar(project, config), config)
    run_id = uuid.uuid4().hex
    out = {'run_id': run_id, 'window': reason, 'writes_enabled': config['business_writes_enabled'], 'tickets': [], 'read_errors': []}
    with Store(project / DB) as store:
        work = {}

        def add(ticket, why):
            work.setdefault(ticket, set()).add(why)

        for action in store.open_actions():
            add(action['ticket'], 'unconfirmed_write')
        if reason == 'allowed':
            today = local_now(now, config).date().isoformat()
            daily = store.meta('last_daily_review') != today
            for ticket in config['allowlist']:
                try:
                    jira = readers['jira'](ticket, config['developer_identity'])
                except ValueError as error:
                    out['read_errors'].append({'ticket': ticket, 'source': 'jira', 'reason': str(error)}); continue
                if not eligible_issue(jira, config):
                    continue
                store.observe(jira, now)
                for obj in config['objects'].get(ticket, []):
                    if obj['owner'] != 'local': continue
                    try:
                        store.observe(readers['object'](obj, ticket), now)
                    except ValueError as error:
                        out['read_errors'].append({'ticket': ticket, 'source': obj['source'], 'object_id': obj['object_id'], 'reason': str(error)})
                for event in store.pending_events(ticket):
                    if event_allowed(event, config): add(ticket, 'changed')
                if daily: add(ticket, 'daily_review')
            for row in store.due(now):
                if row['ticket'] in config['allowlist']: add(row['ticket'], 'check_due')
            if daily: store.set_meta('last_daily_review', today)
            # The same read failure every run is reported once, not every half hour.
            errors_key = stable_key(sorted(json.dumps(e, sort_keys=True) for e in out['read_errors']))
            new_errors = out['read_errors'] and store.meta('last_read_errors') != errors_key
            store.set_meta('last_read_errors', errors_key)
        else:
            new_errors = False
        for ticket in sorted(work):
            out['tickets'].append({'ticket': ticket, 'why': sorted(work[ticket]), 'jira': _jira_brief(store.snapshot(ticket)),
                                   'progress': store.progress(ticket), 'lock': store.lock('ticket:' + ticket),
                                   'open_actions': store.open_actions(ticket=ticket),
                                   'events': [compact(e) for e in store.pending_events(ticket) if event_allowed(e, config)]})
    if out['tickets'] or new_errors:
        out['result'] = 'work'
    else:
        out['result'] = 'idle'; out['reason'] = reason if reason != 'allowed' else 'no_change'
        out.pop('tickets'); out.pop('run_id')
    return out


def _jira_brief(snapshot):
    if not snapshot or snapshot.get('source') != 'jira': return None
    return {k: snapshot.get(k) for k in ('status', 'summary', 'evidence_refs')}


def add_observer(project, ticket, source, object_id, owner):
    path = project / CONFIG
    config = read_config(project)
    if ticket not in config['allowlist']: raise Refused('ticket_not_allowlisted')
    obj = {'source': source, 'object_id': object_id, 'owner': owner}
    validate_observer(obj)
    config['objects'].setdefault(ticket, [])
    if any(o['source'] == source and str(o['object_id']) == str(object_id) for objs in config['objects'].values() for o in objs):
        return {'status': 'already_watched', 'observer': obj}
    config['objects'][ticket].append(obj)
    validate_config(config)
    tmp = path.with_suffix('.json.tmp'); tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n'); tmp.replace(path)
    return {'status': 'watching', 'observer': obj}


def migrate(project):
    path = project / CONFIG
    raw = json.loads(path.read_text())
    upgraded = upgrade_config(raw)
    if upgraded is not raw:
        tmp = path.with_suffix('.json.tmp'); tmp.write_text(json.dumps(upgraded, ensure_ascii=False, indent=2) + '\n'); tmp.replace(path)
    with Store(project / DB) as store:
        version = store.db.execute('PRAGMA user_version').fetchone()[0]
    return {'status': 'migrated', 'config_schema': upgraded['schema_version'], 'db_version': version,
            'writes_enabled': upgraded['business_writes_enabled']}


def main(argv=None, now=None, readers=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', required=True, type=Path, help='workflow project folder (holds config/ and state/)')
    sub = p.add_subparsers(dest='op', required=True)
    sub.add_parser('tick', help='first call of a run: idle, or the tickets that need work')
    sub.add_parser('window', help='may new work start now?')
    sub.add_parser('validate-config')
    sub.add_parser('migrate', help='upgrade a prototype config and state in place')
    s = sub.add_parser('show'); s.add_argument('ticket')
    for name in ('claim', 'release'):
        s = sub.add_parser(name); s.add_argument('resource', help='ticket key, or a shared key such as repo:group/name#branch'); s.add_argument('--owner', required=True)
    s = sub.add_parser('begin', help='record a write before making it')
    s.add_argument('--owner', required=True); s.add_argument('--ticket', required=True); s.add_argument('--kind', required=True)
    s.add_argument('--target', required=True); s.add_argument('--version', default='1', help='what the write is based on, e.g. MR head SHA')
    s.add_argument('--intent', default='{}', help='JSON: the concrete request'); s.add_argument('--retry', action='store_true')
    s = sub.add_parser('end', help='record what a write actually did, from a readback')
    s.add_argument('action_key'); s.add_argument('--owner', required=True); s.add_argument('--status', required=True, choices=['done', 'failed', 'unknown'])
    s.add_argument('--evidence', action='append', default=[]); s.add_argument('--reason', default='')
    s = sub.add_parser('checkpoint', help='where the ticket stands and what comes next')
    s.add_argument('ticket'); s.add_argument('--owner', required=True); s.add_argument('--stage', required=True)
    s.add_argument('--next', required=True, dest='next_step'); s.add_argument('--next-check-at'); s.add_argument('--note', default='')
    s = sub.add_parser('watch', help='follow a DW task, MR or pipeline that belongs to a ticket')
    s.add_argument('ticket'); s.add_argument('--source', required=True, choices=['dw', 'gitlab_mr', 'gitlab_pipeline'])
    s.add_argument('--object-id', required=True); s.add_argument('--owner', default='local', choices=['local', 'dw'])
    a = p.parse_args(argv)
    project = a.project.resolve(); now = now or now_utc()

    if a.op == 'migrate': return migrate(project)
    config = read_config(project)
    if a.op == 'validate-config': return {'valid': True, 'allowlist': config['allowlist'], 'writes_enabled': config['business_writes_enabled']}
    if a.op == 'window': return {'window': window(now, read_calendar(project, config), config)}
    if a.op == 'tick': return tick(project, now, readers or real_readers(project))
    if a.op == 'watch': return add_observer(project, a.ticket, a.source, a.object_id, a.owner)
    with Store(project / DB) as store:
        if a.op == 'show':
            return {'ticket': a.ticket, 'jira': _jira_brief(store.snapshot(a.ticket)), 'progress': store.progress(a.ticket),
                    'lock': store.lock('ticket:' + a.ticket), 'open_actions': store.open_actions(ticket=a.ticket)}
        if a.op in ('claim', 'release'):
            resource = a.resource if ':' in a.resource else 'ticket:' + a.resource
            if a.op == 'release': return store.release(resource, a.owner)
            if resource.startswith('ticket:') and resource[7:] not in config['allowlist']: raise Refused('ticket_not_allowlisted')
            state = window(now, read_calendar(project, config), config)
            if state != 'allowed': raise Refused('outside_window:' + state)
            return store.claim(resource, a.owner, now)
        if a.op == 'begin':
            state = window(now, read_calendar(project, config), config)
            if state != 'allowed': raise Refused('outside_window:' + state)
            if not config['business_writes_enabled']: raise Refused('writes_disabled')
            if a.ticket not in config['allowlist']: raise Refused('ticket_not_allowlisted')
            return store.begin(a.owner, a.ticket, a.kind, a.target, a.version, json.loads(a.intent), a.retry, now)
        if a.op == 'end':
            return store.end(a.action_key, a.owner, a.status, a.evidence, a.reason, now)
        if a.op == 'checkpoint':
            return store.checkpoint(a.ticket, a.owner, a.stage, a.next_step, a.next_check_at, a.note, now)


def run(argv=None, now=None, readers=None):
    try:
        result, code = main(argv, now, readers), 0
    except Refused as refused:
        result, code = {'status': 'refused', 'reason': str(refused)}, 0
    except (ValueError, OSError, KeyError) as error:
        result, code = {'status': 'error', 'error_type': type(error).__name__, 'reason': str(error)[:300]}, 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(run())
