import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cp, mkdtemp, readFile, rm, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { generate } from './contracts.mjs';

const source = fileURLToPath(new URL('../../contracts/schema', import.meta.url));
const cli = fileURLToPath(new URL('./contracts.mjs', import.meta.url));

async function workspace(t) {
  const root = await mkdtemp(join(tmpdir(), 'haike-contracts-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const options = { schemaDir: join(root, 'schema'), outputDir: join(root, 'src'), log: () => {} };
  await cp(source, options.schemaDir, { recursive: true });
  await generate(options);
  return options;
}

test('generation is stable and preserves action response definitions', async (t) => {
  const options = await workspace(t);
  const before = await readFile(join(options.outputDir, 'types/actions.ts'), 'utf8');
  await generate(options);
  assert.equal(await readFile(join(options.outputDir, 'types/actions.ts'), 'utf8'), before);
  assert.match(before, /export interface ActionResult/);
  assert.match(before, /export interface ActionConflict/);
  assert.equal(await generate({ ...options, check: true }), true);
});

test('check exits nonzero, prints a diff and preserves edited generated files', async (t) => {
  const options = await workspace(t);
  const target = join(options.outputDir, 'types/events.ts');
  const changed = '// intentional drift\n';
  await writeFile(target, changed);
  const result = spawnSync(process.execPath, [cli, '--check', '--schema-dir', options.schemaDir, '--output-dir', options.outputDir], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stdout, /--- current\/types\/events.ts/);
  assert.match(result.stdout, /\+\+\+ generated\/types\/events.ts/);
  assert.match(result.stdout, /-\/\/ intentional drift/);
  assert.equal(await readFile(target, 'utf8'), changed);
});

test('constraint-only schema changes are detected in types and runtime validator', async (t) => {
  const options = await workspace(t);
  const schemaPath = join(options.schemaDir, 'events.schema.json');
  const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
  schema.$defs.RunStarted.properties.deadline_ms.exclusiveMinimum = 10;
  await writeFile(schemaPath, JSON.stringify(schema));
  const diffs = [];
  assert.equal(await generate({ ...options, check: true, log: (diff) => diffs.push(diff) }), false);
  assert.match(diffs.join('\n'), /current\/types\/events.ts/);
  assert.match(diffs.join('\n'), /current\/api\/events-schema.ts/);
  assert.match(diffs.join('\n'), /"exclusiveMinimum": 10/);
});

test('missing generated artifacts fail check without recreating them', async (t) => {
  const options = await workspace(t);
  const missing = join(options.outputDir, 'types/snapshot.ts');
  await unlink(missing);
  assert.equal(await generate({ ...options, check: true }), false);
  await assert.rejects(readFile(missing), { code: 'ENOENT' });
});

test('missing input fails before any artifact is written', async (t) => {
  const options = await workspace(t);
  await unlink(join(options.schemaDir, 'snapshot.schema.json'));
  const target = join(options.outputDir, 'types/events.ts');
  await writeFile(target, 'keep this file\n');
  await assert.rejects(generate(options), /export the Python contracts first/);
  assert.equal(await readFile(target, 'utf8'), 'keep this file\n');
});

test('unsupported runtime schemas fail at generation time', async (t) => {
  const options = await workspace(t);
  const schemaPath = join(options.schemaDir, 'events.schema.json');
  const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
  schema.unevaluatedProperties = false;
  await writeFile(schemaPath, JSON.stringify(schema));
  await assert.rejects(generate(options), /unevaluatedProperties is not supported/);
});
