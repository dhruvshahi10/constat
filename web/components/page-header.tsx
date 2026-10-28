import { cn } from "@/lib/utils";

export function PageHeader({ eyebrow, title, description, actions, className }: { eyebrow?: string; title: string; description?: string; actions?: React.ReactNode; className?: string }) {
  return (
    <header className={cn("mb-6 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0">
        {eyebrow ? <p className="eyebrow mb-2">{eyebrow}</p> : null}
        <h1 className="font-heading text-2xl font-normal tracking-tight sm:text-3xl">{title}</h1>
        {description ? <p className="mt-1 max-w-[70ch] text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="eyebrow py-10 text-center" aria-live="polite">
      {label}
    </div>
  );
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
