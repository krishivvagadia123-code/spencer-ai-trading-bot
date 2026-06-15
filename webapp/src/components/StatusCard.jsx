import { AlertCircle } from "lucide-react";

export function StatusCard({ title, message, icon: Icon = AlertCircle }) {
  return (
    <div className="liquid-glass-light flex flex-col items-center justify-center rounded-2xl p-8 text-center">
      <Icon className="mb-4 h-8 w-8 text-[var(--color-muted-dark-text)]" />
      <h3 className="mb-2 font-medium">{title}</h3>
      <p className="max-w-sm text-sm text-[var(--color-muted-dark-text)]">{message}</p>
    </div>
  );
}