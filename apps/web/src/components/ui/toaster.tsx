"use client";

import { Toaster as Sonner } from "sonner";

export function Toaster() {
  return (
    <Sonner
      theme="dark"
      position="bottom-right"
      closeButton
      toastOptions={{
        classNames: {
          toast: "!bg-surface-raised !border-border !text-foreground !shadow-xl",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}
