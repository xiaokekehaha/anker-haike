import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { createTwoFilesPatch } from 'diff';
import { compile } from 'json-schema-to-typescript';
import * as z from 'zod';

const frontend = fileURLToPath(new URL('..', import.meta.url));
const definitions = [
  { name: 'events', title: 'ServerEvent', aliases: "export type PendingKind = Extract<ServerEvent, { type: 'awaiting_input' }>['kind'];\n" },
  { name: 'actions', title: 'ActionRequest', aliases: "export type ActionKind = ActionRequest['kind'];\n" },
  { name: 'snapshot', title: 'SessionSnapshot', aliases: "export type TimelineItem = NonNullable<SessionSnapshot['timeline']>[number];\n" },
];

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function banner(name, json) {
  const digest = createHash('sha256').update(json).digest('hex');
  return `// Generated file. Do not edit; run npm --prefix frontend run contracts:generate.\n// Source: contracts/schema/${name}.schema.json\n// SHA-256: ${digest}`;
}

export async function renderArtifacts(schemaDir) {
  const outputs = new Map();
  for (const { name, title, aliases } of definitions) {
    const path = resolve(schemaDir, `${name}.schema.json`);
    let schema;
    try {
      schema = canonical(JSON.parse(await readFile(path, 'utf8')));
    } catch (error) {
      throw new Error(`Cannot read ${path}; export the Python contracts first.`, { cause: error });
    }
    if (schema.title !== title) throw new Error(`Expected ${title} in ${path}`);
    const json = JSON.stringify(schema, null, 2);
    const header = banner(name, json);
    // 编译器对根 oneOf 不导出未引用的 $defs；通过对象根统一导出所有定义。
    // 包装只用于 TS 生成，运行时校验仍使用未经改写的原始 Schema。
    const { $defs, ...rootSchema } = structuredClone(schema);
    const typeSchema = {
      title: `${title}Schema`,
      type: 'object',
      additionalProperties: false,
      properties: { contract: { $ref: `#/$defs/${title}` } },
      required: ['contract'],
      $defs: { ...$defs, [title]: rootSchema },
    };
    const types = await compile(typeSchema, `${title}Schema`, {
      bannerComment: header,
      unreachableDefinitions: true,
      unknownAny: true,
      style: { singleQuote: true, tabWidth: 2, semi: true, printWidth: 100 },
    });
    outputs.set(`types/${name}.ts`, `${types.trimEnd()}\n\n${aliases}`);
    if (name === 'events') {
      // 转换不支持新 Schema 时在生成/CI 阶段失败，不等到浏览器启动才报错。
      z.fromJSONSchema(schema, { registry: z.registry() });
      outputs.set('api/events-schema.ts', `${header}\nimport * as z from 'zod';\nimport type { ServerEvent } from '../types/events';\n\n// 类型和校验器来自同一份 Schema；此断言只连接动态转换结果与生成的静态类型。\nexport const serverEventSchema = z.fromJSONSchema(${json}, { registry: z.registry() }) as z.ZodType<ServerEvent>;\n`);
    }
  }
  return outputs;
}

export async function generate({
  schemaDir = resolve(frontend, '../contracts/schema'),
  outputDir = resolve(frontend, 'src'),
  check = false,
  log = console.log,
} = {}) {
  // 所有输入都解析成功后再写产物，避免缺少第三份 Schema 时只更新前两份。
  const outputs = await renderArtifacts(schemaDir);
  let clean = true;
  for (const [relativePath, expected] of outputs) {
    const path = resolve(outputDir, relativePath);
    if (check) {
      let actual = '';
      try {
        actual = await readFile(path, 'utf8');
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
      }
      if (actual !== expected) {
        clean = false;
        log(createTwoFilesPatch(`current/${relativePath}`, `generated/${relativePath}`, actual, expected));
      }
    } else {
      await mkdir(dirname(path), { recursive: true });
      await writeFile(path, expected);
      log(`wrote ${relativePath}`);
    }
  }
  if (check) log(clean ? 'Contract artifacts are up to date.' : 'Contract drift detected. Run make contracts to regenerate.');
  return clean;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const { values } = parseArgs({ options: {
      check: { type: 'boolean', default: false },
      'schema-dir': { type: 'string' },
      'output-dir': { type: 'string' },
    } });
    const clean = await generate({ schemaDir: values['schema-dir'], outputDir: values['output-dir'], check: values.check });
    if (!clean) process.exitCode = 1;
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
