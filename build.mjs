import { build } from 'esbuild';
import { mkdir, writeFile } from 'node:fs/promises';
await mkdir('dist/pages', { recursive: true });
await build({ entryPoints: ['workers/edgetunnel/index.js'], outfile: 'dist/pages/_worker.js', bundle: true,
  format: 'esm', platform: 'browser', external: ['cloudflare:sockets'], minify: true });
await writeFile('dist/pages/index.html', '<!doctype html><meta charset="utf-8"><title>edgetunnel-test</title>Independent test environment');
