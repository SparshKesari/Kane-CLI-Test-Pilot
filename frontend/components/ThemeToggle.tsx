"use client";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  // null until mounted so we don't render the wrong icon during hydration.
  const [light, setLight] = useState<boolean | null>(null);

  useEffect(() => {
    setLight(document.documentElement.classList.contains("light"));
  }, []);

  function toggle() {
    const next = !light;
    setLight(next);
    document.documentElement.classList.toggle("light", next);
    try { localStorage.setItem("theme", next ? "light" : "dark"); } catch {}
  }

  return (
    <button
      onClick={toggle}
      aria-label="Toggle light / dark theme"
      title={light ? "Switch to dark" : "Switch to light"}
      className="text-muted hover:text-ink transition-colors text-sm leading-none w-5 text-center"
    >
      {light === null ? "" : light ? "☾" : "☀"}
    </button>
  );
}
