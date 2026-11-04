"use client";

import { Loader2, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { deleteBusinessAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export function DeleteBusinessButton({
  businessId,
  businessName,
  redirectTo,
  compact = false,
}: {
  businessId: string;
  businessName: string;
  /** Navigate here after deletion (used from the detail page). */
  redirectTo?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  function confirm() {
    startTransition(async () => {
      const result = await deleteBusinessAction(businessId);
      if (!result.ok) {
        toast.error(result.message);
        return;
      }
      toast.success(`${businessName} deleted`);
      setOpen(false);
      if (redirectTo) router.push(redirectTo);
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {compact ? (
          <Button variant="ghost" size="icon" aria-label={`Delete ${businessName}`}>
            <Trash2 />
          </Button>
        ) : (
          <Button variant="secondary">
            <Trash2 /> Delete
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {businessName}?</DialogTitle>
          <DialogDescription>
            This permanently removes the business with its contacts, audits, scores and drafts. The
            deletion is recorded in the audit log. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="secondary" disabled={pending}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="danger" onClick={confirm} disabled={pending}>
            {pending ? <Loader2 className="animate-spin" /> : <Trash2 />}
            Delete business
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
