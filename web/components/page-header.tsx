import { cn } from "@/lib/utils";
import { TableSkeleton } from "@/components/skeletons";

export function PageHeader({ eyebrow, title, description, actions, className }: { eyebrow?: string; title: string; description?: string; actions?: React.ReactNode; className?: string }) {
  return (
    <header className={cn("mb-5 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="eyebrow mb-1.5">{eyebrow}</p> : null}
        <h1 className="font-heading text-[30px] leading-[34px] font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1.5 max-w-[70ch] text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Default loading state: a table-shaped skeleton. Screens with another shape use components/skeletons. */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <TableSkeleton aria-label={label} />;
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div role="alert" className="rounded-md border border-status-critical/40 bg-status-critical-wash p-4 text-sm">
      <p className="eyebrow mb-1 text-status-critical">Could not load</p>
      <p>{error.message}</p>
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-md border border-dashed p-8 text-center">
      <p className="font-heading text-lg">{title}</p>
      {body ? <p className="mt-1 text-sm text-muted-foreground">{body}</p> : null}
    </div>
  );
}
