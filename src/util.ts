export function genRanHex(size: number): string {
  return [...Array(size)].map(() => Math.floor(Math.random() * 16).toString(16)).join('');
}

// returns a new object with the values at each key mapped using mapFn(value)
export function objectMap(object, mapFn): object {
  return Object.keys(object).reduce(function(result, key) {
    result[key] = mapFn(object[key])
    return result
  }, {})
}
