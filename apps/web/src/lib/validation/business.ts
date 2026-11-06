import { BUSINESS_STATUSES } from "@leadforge/shared";
import { z } from "zod";

const optionalText = (max: number) => z.string().trim().max(max, `Must be ${max} characters or fewer`);

/**
 * Client-side mirror of the API's BusinessCreate rules for instant feedback.
 * The API remains authoritative (including the public-URL safety checks).
 */
export const businessFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200, "Must be 200 characters or fewer"),
  website_url: optionalText(2048).refine(
    (value) => value === "" || /^(https?:\/\/)?[^\s/$.?#][^\s]*\.[^\s]{2,}$/i.test(value),
    "Enter a website such as example.com",
  ),
  industry: optionalText(120),
  city: optionalText(120),
  region: optionalText(120),
  country_code: z
    .string()
    .trim()
    .refine((value) => value === "" || /^[A-Za-z]{2}$/.test(value), "Use a 2-letter country code"),
  phone: z
    .string()
    .trim()
    .refine((value) => value === "" || /^[0-9+().\- ]{5,40}$/.test(value), "Enter a valid phone number"),
  email: z
    .string()
    .trim()
    .max(320, "Must be 320 characters or fewer")
    .refine((value) => value === "" || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value), "Enter a valid email address"),
  description: optionalText(5000),
  source_url: optionalText(2048).refine(
    (value) => value === "" || /^(https?:\/\/)?[^\s/$.?#][^\s]*\.[^\s]{2,}$/i.test(value),
    "Enter a web address",
  ),
  notes: optionalText(5000),
  status: z.enum(BUSINESS_STATUSES),
});

export type BusinessFormValues = z.infer<typeof businessFormSchema>;

export const emptyBusinessForm: BusinessFormValues = {
  name: "",
  website_url: "",
  industry: "",
  city: "",
  region: "",
  country_code: "",
  phone: "",
  email: "",
  description: "",
  source_url: "",
  notes: "",
  status: "new",
};

export const organizationFormSchema = z.object({
  name: z.string().trim().min(2, "At least 2 characters").max(120, "Must be 120 characters or fewer"),
});
