"""Checkpoint persistence and observation shared by the one-pass evaluation runners."""

import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace


RAW_KEYS = {
    'action', 'protocol', 'token_in', 'token_out', 'amount', 'chain',
    'unsupported_action', 'slippage', 'unhandled_constraints',
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def save(path, value):
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', dir=path.parent,
        prefix=path.stem + '-', suffix='.tmp', delete=False,
    ) as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
        stream.write('\n')
        temp = Path(stream.name)
    # Windows indexers can briefly hold a reader on a checkpoint.
    for attempt in range(10):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.2 * (attempt + 1))


def journal(path, value):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, default=str) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def field_checks(expected, actual):
    if expected is None:
        return None
    actual = actual or {}
    result = {}
    for key, value in expected.items():
        found = actual.get(key)
        if key == 'amount' and value is not None and found is not None:
            try:
                equal = Decimal(str(value)) == Decimal(str(found))
            except InvalidOperation:
                equal = False
        else:
            equal = found == value
        result[key] = {'expected': value, 'actual': found, 'matches': equal}
    # Omitted slippage must stay omitted in the interpreted intent.
    if 'slippage_bps' not in result:
        result['slippage_bps'] = {
            'expected': None,
            'actual': actual.get('slippage_bps'),
            'matches': actual.get('slippage_bps') is None,
        }
    return result


def raw_shape(value):
    if not isinstance(value, dict):
        return False
    if set(value) != RAW_KEYS:
        return False
    if any(value[k] is not None and not isinstance(value[k], str)
           for k in RAW_KEYS - {'slippage', 'unhandled_constraints'}):
        return False
    if not isinstance(value['unhandled_constraints'], list) or not all(
        isinstance(v, str) for v in value['unhandled_constraints']
    ):
        return False
    slip = value['slippage']
    return slip is None or (
        isinstance(slip, dict) and set(slip) == {'value', 'unit'}
        and isinstance(slip['value'], str) and slip['unit'] in {'bps', 'percent'}
    )


def stable_snapshot(facts):
    # Exclude wall-clock ages and audit timestamps, but retain synchronization state.
    return {k: facts[k] for k in ['deployments', 'contracts', 'reserves', 'pools', 'invariants']}


def saved_interpretations(path):
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['id'] in rows:
            raise ValueError('Duplicate saved interpretation; do not silently select a retry')
        rows[row['id']] = row
    return rows


class Observer:

    def __init__(self, folder, client_factory):
        self.folder = folder
        self.client_factory = client_factory
        self.case_id = None
        self.attempts = []
        self.extra_wait = 0

    def client(self):
        # A transport timeout prevents a model thread outliving its observation context.
        underlying = self.client_factory().with_options(timeout=45.0)

        def create(**kwargs):
            attempt = {
                'case_id': self.case_id,
                'outer_attempt': len(self.attempts) + 1,
                'started_at_utc': utc(),
            }
            journal(self.folder / 'provider_attempts.jsonl', {'event': 'started', **attempt})
            start = time.perf_counter()
            try:
                response = underlying.chat.completions.with_raw_response.create(**kwargs)
                parsed = response.parse()
                headers = {
                    k: v for k, v in response.headers.items()
                    if k.lower().startswith('x-ratelimit-') or k.lower() == 'retry-after'
                }
                attempt.update(
                    success=True, raw_text=parsed.choices[0].message.content,
                    response_model=parsed.model,
                    usage=parsed.usage.model_dump() if parsed.usage else None,
                    rate_limit_headers=headers,
                )
                remaining = headers.get('x-ratelimit-remaining-tokens')
                reset = headers.get('x-ratelimit-reset-tokens', '')
                if remaining is not None and int(remaining) < 1600:
                    units = {'ms': 0.001, 's': 1, 'm': 60, 'h': 3600}
                    seconds = sum(float(n) * units[u]
                                  for n, u in re.findall(r'([0-9.]+)(ms|s|m|h)', reset))
                    self.extra_wait = max(self.extra_wait, min(seconds + 1, 300))
                return parsed
            except Exception as exc:
                attempt.update(
                    success=False, error_type=type(exc).__name__,
                    http_status=getattr(exc, 'status_code', None),
                )
                if getattr(exc, 'status_code', None) == 429:
                    message = str(exc).lower()
                    scopes = {
                        'tokens_per_minute': ['tpm', 'tokens per minute'],
                        'tokens_per_day': ['tpd', 'tokens per day'],
                        'requests_per_day': ['rpd', 'requests per day'],
                    }
                    attempt['rate_limit_scope'] = [
                        name for name, terms in scopes.items()
                        if any(term in message for term in terms)
                    ]
                    self.extra_wait = max(self.extra_wait, 60)
                raise
            finally:
                attempt.update(
                    completed_at_utc=utc(),
                    wall_latency_ms=round((time.perf_counter() - start) * 1000, 3),
                )
                self.attempts.append(attempt)
                journal(self.folder / 'provider_attempts.jsonl', {'event': 'completed', **attempt})
                underlying.close()
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
