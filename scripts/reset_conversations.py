"""Reset disposable conversation data in this project's DB; preview unless --apply.

Stop orchestrator before applying. Product/knowledge/configuration tables are not touched.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orchestrator'))
from app.settings import settings

TABLES = [('public', name) for name in (
    'sessions', 'session_events', 'session_inputs', 'session_actions', 'session_images',
    'conversation_summaries', 'checkpoints', 'checkpoint_blobs', 'checkpoint_writes',
    # 售后案件与服务单都绑定在会话上，随会话一起清
    'satisfaction_ratings', 'human_decisions', 'action_executions', 'case_events', 'service_episodes',
    'cases', 'service_orders',
)] + [('analytics', name) for name in (
    'cases', 'model_calls', 'retrieval_calls', 'node_runs', 'run_facts', 'session_facts',
)]
PRESERVED = ('products', 'plans', 'catalog_meta', 'sku_fault_cards')

async def main(args):
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        database = (await (await conn.execute('select current_database()')).fetchone())[0]
        if database != args.database:
            raise RuntimeError('Connected database does not match explicitly selected project database')
        existing = []
        for schema, table in TABLES:
            row = await (await conn.execute('select to_regclass(%s)', (f'{schema}.{table}',))).fetchone()
            if row[0]:
                existing.append((schema, table))
        names = sql.SQL(', ').join(sql.Identifier(*name) for name in existing)
        if args.apply:
            await conn.execute(sql.SQL('LOCK TABLE {} IN ACCESS EXCLUSIVE MODE').format(names))
        async def counts(tables):
            result = {}
            for name in tables:
                row = await (await conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(*name)))).fetchone()
                result['.'.join(name)] = row[0]
            return result
        before = await counts(existing)
        preserve_before = await counts([('public', name) for name in PRESERVED])
        if args.apply:
            await conn.execute(sql.SQL('TRUNCATE TABLE {}').format(names))
        after = await counts(existing)
        preserve_after = await counts([('public', name) for name in PRESERVED])
        assert preserve_before == preserve_after
        if args.apply:
            assert not any(after.values())
        print(json.dumps(dict(database=database, applied=args.apply, before=before, after=after,
                             preserved=preserve_after), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    asyncio.run(main(parser.parse_args()))
