import { getWords } from './randomWords.js';

let counter: number = 0;

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function genRanHex(_size: number): string {
  const words = getWords();
  // return words[Math.floor(Math.random() * words.length)];
  return words[counter++];
  // return [...Array(size)].map(() => Math.floor(Math.random() * 16).toString(16)).join('');
}