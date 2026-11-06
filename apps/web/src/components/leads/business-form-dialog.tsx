"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BUSINESS_STATUSES, type BusinessRead } from "@leadforge/shared";
import { Loader2, Pencil, Plus } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { createBusinessAction, updateBusinessAction, type ActionResult, type DuplicateDetails } from "@/app/actions";
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
import { businessFormSchema, emptyBusinessForm, type BusinessFormValues } from "@/lib/validation/business";

type FieldName = keyof BusinessFormValues;

function toFormValues(business: BusinessRead): BusinessFormValues {
  return {
    name: business.name,
    website_url: business.website_url ?? "",
    industry: business.industry ?? "",
    city: business.city ?? "",
    region: business.region ?? "",
    country_code: business.country_code ?? "",
    phone: business.phone ?? "",
    email: business.email ?? "",
    description: business.description ?? "",
    source_url: business.source_url ?? "",
    notes: business.notes ?? "",
    status: business.status,
  };
}

export function BusinessFormDialog({
  business,
  defaultOpen = false,
}: {
  /** Edit this business; omit to add a new one. */
  business?: BusinessRead;
  defaultOpen?: boolean;
}) {
  const initial = business ? toFormValues(business) : emptyBusinessForm;
  const [open, setOpen] = useState(defaultOpen);
  const [duplicate, setDuplicate] = useState<DuplicateDetails | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const form = useForm<BusinessFormValues>({
    resolver: zodResolver(businessFormSchema),
    defaultValues: initial,
  });
  const { errors, isSubmitting } = form.formState;

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      form.reset(business ? toFormValues(business) : emptyBusinessForm);
      setDuplicate(null);
      // Drop the ?new=1 deep-link flag so a refresh does not reopen the dialog.
      if (defaultOpen) router.replace(pathname);
    }
  }

  async function save(values: BusinessFormValues, allowDuplicate: boolean) {
    setDuplicate(null);
    const result: ActionResult<BusinessRead> = business
      ? await updateBusinessAction(business.id, values, allowDuplicate)
      : await createBusinessAction(values, allowDuplicate);
    if (!result.ok) {
      if (result.duplicate) {
        setDuplicate(result.duplicate);
        return;
      }
      for (const [field, message] of Object.entries(result.fieldErrors ?? {})) {
        if (field in emptyBusinessForm) form.setError(field as FieldName, { message });
      }
      if (!result.fieldErrors) toast.error(result.message);
      return;
    }
    toast.success(business ? "Changes saved" : `${result.data.name} added`, {
      description: result.data.domain ?? undefined,
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
        {business ? (
          <Button variant="secondary">
            <Pencil /> Edit
          </Button>
        ) : (
          <Button>
            <Plus /> Add business
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{business ? `Edit ${business.name}` : "Add a business"}</DialogTitle>
          <DialogDescription>
            Only public websites are accepted. You will be told if this looks like a business you already have.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={form.handleSubmit((values) => save(values, false))} noValidate className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">{field("name", "Business name", { placeholder: "Riverside Dental", autoFocus: true })}</div>
          {field("website_url", "Website", { placeholder: "riverside-dental.com", inputMode: "url" })}
          {field("email", "Email", { type: "email", placeholder: "hello@riverside-dental.com" })}
          {field("industry", "Category", { placeholder: "Dental clinic" })}
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
          {field("country_code", "Country code", { placeholder: "US", maxLength: 2 })}
          {field("city", "City")}
          {field("region", "Region / state")}
          {field("phone", "Phone", { inputMode: "tel" })}
          <div className="sm:col-span-2">{field("source_url", "Source URL", { placeholder: "Where you found this business", inputMode: "url" })}</div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="business-description">Description</Label>
            <Textarea id="business-description" rows={2} aria-invalid={Boolean(errors.description)} {...form.register("description")} />
            <FieldError message={errors.description?.message} />
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="business-notes">Notes</Label>
            <Textarea id="business-notes" rows={2} aria-invalid={Boolean(errors.notes)} {...form.register("notes")} />
            <FieldError message={errors.notes?.message} />
          </div>
          {duplicate ? (
            <div role="alert" className="rounded-lg border border-warning/30 bg-warning/8 px-4 py-3 text-sm sm:col-span-2">
              <p className="font-medium text-warning">This may already exist</p>
              <p className="mt-1 text-muted-foreground">
                {duplicate.reason ?? "A matching business exists"}: {duplicate.name ?? duplicate.domain}.
                {" "}If it really is a different business, you can save it separately.
              </p>
            </div>
          ) : null}
          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="secondary" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            {duplicate ? (
              <Button type="button" disabled={isSubmitting} onClick={form.handleSubmit((values) => save(values, true))}>
                {isSubmitting ? <Loader2 className="animate-spin" /> : null}
                Save as separate business
              </Button>
            ) : (
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="animate-spin" /> : null}
                {business ? "Save changes" : "Save business"}
              </Button>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
