/**
 * Copy data/ directory and categories.json into public/ at build time.
 * Runs before `astro build` so the data is available in the built site.
 */
import { cpSync, copyFileSync, existsSync, mkdirSync } from 'fs';
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

const catSrc = join(root, 'categories.json');
const catDest = join(root, 'public', 'categories.json');
if (existsSync(catSrc)) {
  copyFileSync(catSrc, catDest);
  console.log('✅ categories.json copied to public/categories.json');
} else {
  console.warn('⚠️  categories.json not found — skipping');
}
