from datetime import time
from zoneinfo import ZoneInfo


def _hm(value):
    hours, minutes = value.split(':')
    return time(int(hours), int(minutes))


def local_now(now, config):
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    return now.astimezone(ZoneInfo(config['timezone']))


def window(now, years, config):
    """'allowed' or the reason new work may not start. Fails closed on an unverified year."""
    local = local_now(now, config)
    year = years.get(str(local.year))
    if not year or year.get('verified') is not True:
        return 'calendar_not_covered'
    if local.weekday() not in config['working_days']:
        return 'weekend'
    if local.date().isoformat() in year['dates']:
        return 'holiday'
    if not _hm(config['start']) <= local.time().replace(tzinfo=None) < _hm(config['end']):
        return 'outside_window'
    return 'allowed'
