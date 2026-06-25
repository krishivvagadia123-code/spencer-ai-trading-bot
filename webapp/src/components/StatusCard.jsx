export function StatusCard({ title, message }) {
  return (
    <div className="status-card liquid-glass-light flex min-h-[132px] flex-col justify-center rounded-2xl p-6">
      <h3 className="font-display text-[20px] font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed">{message}</p>
    </div>
  );
}
