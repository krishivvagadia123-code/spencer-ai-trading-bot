import { useState } from "react";

export function Profile({ profile, setProfile }) {
  const [form, setForm] = useState(profile);

  const handleSave = (e) => {
    e.preventDefault();
    setProfile(form);
    alert("Profile saved locally");
  };

  return (
    <div className="liquid-glass-light mx-auto max-w-xl rounded-2xl p-8">
      <h2 className="mb-6 text-2xl font-light tracking-tight">Trader Profile</h2>
      <form onSubmit={handleSave} className="space-y-6">
        <div>
          <label className="mb-2 block text-sm font-medium">Display Name</label>
          <input
            type="text"
            value={form.name}
            onChange={e => setForm({...form, name: e.target.value})}
            className="w-full rounded-lg border border-[var(--color-light-border)] bg-white px-4 py-2.5 outline-none focus:border-black"
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">Bot Profile Name</label>
          <input
            type="text"
            value={form.botName}
            onChange={e => setForm({...form, botName: e.target.value})}
            className="w-full rounded-lg border border-[var(--color-light-border)] bg-white px-4 py-2.5 outline-none focus:border-black"
          />
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">Trade Type</label>
          <select
            value={form.tradeType}
            onChange={e => setForm({...form, tradeType: e.target.value})}
            className="w-full rounded-lg border border-[var(--color-light-border)] bg-white px-4 py-2.5 outline-none focus:border-black"
          >
            <option value="Paper Journal">Paper Journal</option>
            <option value="Observe Only">Observe Only</option>
            <option value="Manual Review">Manual Review</option>
          </select>
        </div>
        <div>
          <label className="mb-2 block text-sm font-medium">Risk Mode</label>
          <select
            value={form.risk}
            onChange={e => setForm({...form, risk: e.target.value})}
            className="w-full rounded-lg border border-[var(--color-light-border)] bg-white px-4 py-2.5 outline-none focus:border-black"
          >
            <option value="Capital Defense">Capital Defense</option>
            <option value="Balanced">Balanced</option>
            <option value="Manual Approval Only">Manual Approval Only</option>
            <option value="Conservative Review">Conservative Review</option>
          </select>
        </div>
        <button type="submit" className="w-full rounded-lg bg-[var(--color-primary-black)] py-3 text-sm font-medium text-white transition-opacity hover:opacity-90">
          Save Changes
        </button>
      </form>
    </div>
  );
}
