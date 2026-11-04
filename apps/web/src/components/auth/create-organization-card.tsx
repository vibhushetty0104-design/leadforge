"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import type { z } from "zod";

import { createOrganizationAction } from "@/app/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FieldError, Input, Label } from "@/components/ui/input";
import { organizationFormSchema } from "@/lib/validation/business";

type Values = z.infer<typeof organizationFormSchema>;

export function CreateOrganizationCard() {
  const form = useForm<Values>({ resolver: zodResolver(organizationFormSchema), defaultValues: { name: "" } });

  async function onSubmit(values: Values) {
    const result = await createOrganizationAction(values);
    if (result.ok) toast.success(`Created ${result.data.organization.name}`);
    else form.setError("name", { message: result.message });
  }

  return (
    <Card className="mx-auto mt-6 max-w-lg">
      <CardHeader>
        <span className="mb-2 w-fit rounded-md bg-primary/10 p-2 ring-1 ring-primary/20">
          <Building2 aria-hidden className="size-5 text-primary-hover" />
        </span>
        <CardTitle className="text-base">Create your organization</CardTitle>
        <CardDescription>
          Leads, audits and campaigns belong to an organization. You will be its owner and can
          invite teammates later.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="org-name">Organization name</Label>
            <Input
              id="org-name"
              placeholder="e.g. Northwind Studio"
              autoComplete="organization"
              aria-invalid={Boolean(form.formState.errors.name)}
              {...form.register("name")}
            />
            <FieldError message={form.formState.errors.name?.message} />
          </div>
          <Button type="submit" disabled={form.formState.isSubmitting} className="self-start">
            {form.formState.isSubmitting ? <Loader2 className="animate-spin" /> : null}
            Create organization
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
