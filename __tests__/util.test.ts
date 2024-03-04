import { genRanHex } from "../src/util.js";

describe('genRanHex', () => {
    it('returns a string of the correct length', () => {
        expect(genRanHex(4).length).toBe(4);
    });
});