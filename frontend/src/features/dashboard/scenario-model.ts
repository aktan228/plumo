/** Same bounded literal phrase contract as the server; phrases are never regex. */
export function validHandoffPhrases(value: string): boolean {
  const lines = value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  return lines.length <= 10 && lines.every(line => Array.from(line).length >= 2 && Array.from(line).length <= 100 && /[\p{L}\p{N}]/u.test(line));
}
