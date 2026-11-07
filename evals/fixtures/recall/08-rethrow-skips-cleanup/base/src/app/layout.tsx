import type { ReactNode } from "react";
import { DialogProvider } from "../components/DialogProvider";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <DialogProvider>{children}</DialogProvider>
      </body>
    </html>
  );
}
