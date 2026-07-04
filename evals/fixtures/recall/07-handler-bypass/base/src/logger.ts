export const logger = {
  error(code: string, err: unknown): void {
    console.error(`[error] ${code}`, err);
  },
  info(message: string): void {
    console.info(`[info] ${message}`);
  },
};
