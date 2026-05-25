const BLOCK_NUMBER_FORMAT = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
  useGrouping: true,
});

export function formatBlockNumber(value: number): string {
  return BLOCK_NUMBER_FORMAT.format(value);
}
