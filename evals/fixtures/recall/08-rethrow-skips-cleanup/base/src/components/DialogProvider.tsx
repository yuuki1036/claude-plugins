"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type DialogApi = {
  openDialog: (content: ReactNode) => void;
  closeDialog: () => void;
};

const DialogContext = createContext<DialogApi | null>(null);

export function DialogProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode>(null);
  const api: DialogApi = {
    openDialog: (next) => setContent(next),
    closeDialog: () => setContent(null),
  };
  return (
    <DialogContext.Provider value={api}>
      {children}
      {content !== null && <dialog open>{content}</dialog>}
    </DialogContext.Provider>
  );
}

export function useDialog(): DialogApi {
  const api = useContext(DialogContext);
  if (!api) throw new Error("useDialog must be used within DialogProvider");
  return api;
}
