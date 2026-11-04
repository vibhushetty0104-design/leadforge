"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BUSINESS_STATUSES } from "@leadforge/shared";
import { Loader2, Plus } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { createBusinessAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FieldError, Input, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { humanize } from "@/lib/format";
import {
  businessFormSchema,
  emptyBusinessForm,
  type BusinessFormValues,
} from "@/lib/validation/business";

type FieldName = keyof BusinessFormValues;

export function AddBusinessDialog({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const router = useRouter();
  const pathname = usePathname();
  const form = useForm<BusinessFormValues>({
    resolver: zodResolver(businessFormSchema),
    defaultValues: emptyBusinessForm,
  });
  const { errors, isSubmitting } = form.formState;

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      form.reset(emptyBusinessForm);
      // Drop the ?new=1 deep-link flag so a refresh does not reopen the dialog.
      if (defaultOpen) router.replace(pathname);
    }
  }

  async function onSubmit(values: BusinessFormValues) {
    const result = await createBusinessAction(values);
    if (!result.ok) {
      for (const [field, message] of Object.entries(result.fieldErrors ?? {})) {
        if (field in emptyBusinessForm) form.setError(field as FieldName, { message });
      }
      if (!result.fieldErrors) toast.error(result.message);
      return;
    }
    toast.success(`${result.data.name} added`, {
      description: result.data.domain ?? "No website recorded",
    });
    handleOpenChange(false);
  }

  const field = (name: FieldName, label: string, props: React.ComponentProps<typeof Input> = {}) => (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={`business-${name}`}>{label}</Label>
      <Input id={`business-${name}`} aria-invalid={Boolean(errors[name])} {...props} {...form.register(name)} />
      <FieldError message={errors[name]?.message} />
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> Add business
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a business</DialogTitle>
          <DialogDescription>
            Record a prospect you have found. Only public websites are accepted; duplicates are
            detected by domain.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">{field("name", "Business name", { placeholder: "Riverside Dental", autoFocus: true })}</div>
          <div className="sm:col-span-2">
            {field("website_url", "Website", { placeholder: "riverside-dental.com", inputMode: "url" })}
          </div>
          {field("industry", "Industry", { placeholder: "Dental clinic" })}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="business-status">Status</Label>
            <NativeSelect id="business-status" {...form.register("status")}>
              {BUSINESS_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </NativeSelect>
          </div>
          {field("city", "City")}
          {field("region", "Region / state")}
          {field("country_code", "Country code", { placeholder: "US", maxLength: 2 })}
          {field("phone", "Phone", { inputMode: "tel" })}
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="business-notes">Notes</Label>
            <Textarea id="business-notes" rows={3} aria-invalid={Boolean(errors.notes)} {...form.register("notes")} />
            <FieldError message={errors.notes?.message} />
          </div>
          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="secondary" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" /> : null}
              Save business
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
