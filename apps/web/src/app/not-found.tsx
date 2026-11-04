import { Compass } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/data/states";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-lg items-center px-4">
      <EmptyState
        className="w-full"
        icon={Compass}
        title="Page not found"
        description="The page you were looking for does not exist or you do not have access to it."
        action={
          <Button asChild variant="secondary">
            <Link href="/dashboard">Back to dashboard</Link>
          </Button>
        }
      />
    </main>
  );
}
