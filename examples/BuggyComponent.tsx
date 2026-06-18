// Intentionally buggy React component for demoing ui-ux-doctor.
// Run:  python3 scripts/scan.py examples/BuggyComponent.tsx
import React, { useEffect, useState } from "react";

export function ProductList({ products }) {
  const [data, setData] = useState([]);

  // Bug: no dependency array -> refetches on every render (infinite loop risk)
  useEffect(() => {
    fetch("http://localhost:8000/api/products")  // Bug: hardcoded host
      .then((r) => r.json())
      .then(setData);
  });

  console.log("rendering", data); // Bug: leftover debug log

  return (
    <div>
      {/* Bug: 0 leaks into the UI when the list is empty */}
      {products.length && <h2>Featured</h2>}

      {/* Bug: clickable div, not keyboard accessible */}
      <div onClick={() => alert("hi")}>Open menu</div>

      <ul>
        {products.map((p, index) => (
          // Bug: index as key + missing img alt
          <li key={index} style={{ padding: 8 }}>
            <img src={p.img} />
            {/* Bug: icon-only button with no accessible name */}
            <button onClick={() => setData([])}>
              <svg viewBox="0 0 24 24" width="16" height="16" />
            </button>
          </li>
        ))}
      </ul>

      {/* Bug: dangerouslySetInnerHTML */}
      <div dangerouslySetInnerHTML={{ __html: data.description }} />
    </div>
  );
}
