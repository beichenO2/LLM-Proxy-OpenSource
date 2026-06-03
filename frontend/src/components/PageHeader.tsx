import type { ReactNode } from "react";

interface IPageHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export default function PageHeader({ title, description, action }: IPageHeaderProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-100">{title}</h1>
        {description ? <p className="mt-1 text-neutral-600 dark:text-neutral-400">{description}</p> : null}
      </div>
      {action ?? null}
    </div>
  );
}
