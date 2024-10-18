export function scale(amountStr: string, filetype: string, LEDGER_SCALE: number, ROUNDING_MARGIN: number): number {
  const amount = parseFloat(amountStr);
  if (isNaN(amount)) {
    throw new Error(`Cannot parse float '${amountStr}'`);
  }
  const scaledAmount = Math.round(amount * LEDGER_SCALE);
  if (Math.abs(scaledAmount - amount * LEDGER_SCALE) > ROUNDING_MARGIN) {
    throw new Error(`Ledger scale insufficient for amount in ${filetype} file: ${amountStr} -> ${amount * LEDGER_SCALE} -> ${scaledAmount}`);
  }
  return scaledAmount;
}