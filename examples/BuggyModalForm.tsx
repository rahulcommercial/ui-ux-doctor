// Intentionally buggy modal + form + theming for demoing ui-ux-doctor.
// Run:  python3 scripts/scan.py examples/BuggyModalForm.tsx
import React, { useState } from "react";

export function SettingsModal({ onClose }) {
  const [email, setEmail] = useState("");

  return (
    // Bug: modal with no role/aria-modal, no Escape handler in this file,
    // hardcoded white bg (no dark mode), light-only Tailwind class.
    <div className="modal bg-white" style={{ background: "#fff" }}>
      <aside className="sidebar">Navigation</aside>

      {/* Bug: form has no onSubmit -> Enter reloads the page */}
      <form>
        {/* Bug: input + textarea with no label (placeholder is not a label) */}
        <input type="email" placeholder="Email" value={email}
               onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="Password" />
        <textarea placeholder="Notes" />

        {/* Bug: nested interactive -> button inside an anchor */}
        <a href="/save">
          <button type="button">Save</button>
        </a>
      </form>
    </div>
  );
}
