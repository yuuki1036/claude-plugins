export class InputError extends Error {}

const MAX_LENGTH = 40;

export function parseProjectName(value: FormDataEntryValue | null): string {
  const name = typeof value === "string" ? value.trim() : "";
  if (name === "") throw new InputError("名前を入力してください");
  if (name.length > MAX_LENGTH) throw new InputError(`名前は ${MAX_LENGTH} 文字以内で入力してください`);
  return name;
}
