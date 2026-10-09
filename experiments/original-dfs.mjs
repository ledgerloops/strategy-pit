// Run the unmodified historical implementation without src/dfs.ts's hard-coded
// one-loop debugging check. Build first with the repository's pinned Node/npm.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { BirdsEyeWorm } from '../build/src/BirdsEyeWorm.js';

const [input, output] = process.argv.slice(2);
if (!input || !output || resolve(input) === resolve(output)) {
  throw new Error('Usage: node experiments/original-dfs.mjs INPUT.csv OUTPUT.csv (different paths)');
}
const worm = new BirdsEyeWorm(false, output);
for (const line of readFileSync(input, 'utf8').trim().split('\n')) {
  const [from, to, amount] = line.trim().split(/\s+/);
  worm.addTransfer(from, to, Number(amount));
}
await worm.runWorm();
