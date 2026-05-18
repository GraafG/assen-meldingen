/**
 * Copy data/ directory into dist/data/ at build time.
 * Runs before `astro build` so the data is available in the built site.
 */
import { cpSync, existsSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const root = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]scripts$/, '');
const src = join(root, 'data');
const dest = join(root, 'public', 'data');

if (!existsSync(src)) {
  console.warn('⚠️  data/ not found — skipping copy');
  process.exit(0);
}

mkdirSync(dest, { recursive: true });
cpSync(src, dest, { recursive: true });
console.log('✅ data/ copied to public/data/');
