const fs = require('fs');

let css = fs.readFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', 'utf-8');

const lightVars = `
.dashboard-light {
  --color-white: #ffffff !important;
  --color-gray-50: #f9fafb !important;
  --color-gray-100: #f3f4f6 !important;
  --color-gray-200: #e5e7eb !important;
  --color-gray-300: #d1d5db !important;
  --color-gray-400: #9ca3af !important;
  --color-gray-500: #6b7280 !important;
  --color-gray-600: #4b5563 !important;
  --color-gray-700: #374151 !important;
  --color-gray-800: #1f2937 !important;
  --color-gray-900: #111827 !important;
  
  --color-blue-50: #eff6ff !important;
  --color-blue-100: #dbeafe !important;
  --color-blue-200: #bfdbfe !important;
  --color-blue-500: #3b82f6 !important;
  --color-blue-600: #2563eb !important;
  --color-blue-700: #1d4ed8 !important;
  
  --color-emerald-50: #ecfdf5 !important;
  --color-emerald-100: #d1fae5 !important;
  --color-emerald-200: #a7f3d0 !important;
  --color-emerald-400: #34d399 !important;
  --color-emerald-500: #10b981 !important;
  --color-emerald-600: #059669 !important;
  --color-emerald-700: #047857 !important;
  
  --color-green-50: #f0fdf4 !important;
  --color-green-100: #dcfce7 !important;
  --color-green-200: #bbf7d0 !important;
  --color-green-400: #4ade80 !important;
  --color-green-500: #22c55e !important;
  --color-green-600: #16a34a !important;
  --color-green-700: #15803d !important;

  --color-red-50: #fef2f2 !important;
  --color-red-100: #fee2e2 !important;
  --color-red-200: #fecaca !important;
  --color-red-400: #f87171 !important;
  --color-red-500: #ef4444 !important;
  --color-red-600: #dc2626 !important;
  --color-red-700: #b91c1c !important;
  
  --color-rose-50: #fff1f2 !important;
  --color-rose-100: #ffe4e6 !important;
  --color-rose-200: #fecdd3 !important;
  --color-rose-400: #fb7185 !important;
  --color-rose-500: #f43f5e !important;
  --color-rose-600: #e11d48 !important;

  --color-amber-50: #fffbeb !important;
  --color-amber-100: #fef3c7 !important;
  --color-amber-200: #fde68a !important;
  --color-amber-400: #fbbf24 !important;
  --color-amber-500: #f59e0b !important;
  --color-amber-600: #d97706 !important;
  --color-amber-700: #b45309 !important;
}
`;

if (!css.includes('--color-white: #ffffff !important;')) {
  css = css.replace('.dashboard-light {', lightVars + '\n.dashboard-light {');
  fs.writeFileSync('C:/Users/krish/OneDrive/Desktop/AI TRADE/frontend/src/index.css', css);
  console.log('Injected override vars into index.css');
} else {
  console.log('Vars already injected');
}
