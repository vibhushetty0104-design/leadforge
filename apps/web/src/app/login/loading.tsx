import { Skeleton } from "@/components/ui/skeleton";

export default function LoginLoading() {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4" aria-busy aria-label="Loading">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <Skeleton className="size-10 rounded-lg" />
          <Skeleton className="h-6 w-52" />
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    </main>
  );
}
