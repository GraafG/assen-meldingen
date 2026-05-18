import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://graafg.github.io',
  base: '/assen-meldingen',
  output: 'static',
  build: { format: 'directory' },
});
