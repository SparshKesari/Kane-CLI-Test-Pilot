import "./globals.css";
import type { Metadata } from "next";
import { ThemeToggle } from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "KaneCLI TestPilot",
  description: "Paste a repo. Get real, browser-verified end-to-end tests — driven by Kane CLI — opened as a PR.",
};

// Runs before paint: defaults to dark, applies a saved light preference with no flash.
const themeInit = `(function(){try{if(localStorage.getItem('theme')==='light')document.documentElement.classList.add('light');}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="font-sans antialiased min-h-screen flex flex-col">
        <header className="border-b border-line bg-cream/80 backdrop-blur sticky top-0 z-10">
          <div className="mx-auto max-w-5xl px-6 py-4 flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-term flex items-center justify-center text-clay-soft text-sm leading-none">►</div>
            <a href="/" className="font-serif text-lg tracking-tight">
              KaneCLI <span className="text-clay">TestPilot</span>
            </a>
            <nav className="ml-auto flex items-center gap-4 text-xs">
              <a href="/how-it-works" className="text-muted hover:text-ink">How it works</a>
              <a href="https://www.testmuai.com/kane-cli/" target="_blank" rel="noreferrer"
                 className="text-muted hover:text-ink">powered by Kane CLI</a>
              <ThemeToggle />
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-10 w-full flex-1">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-5xl px-6 py-6 text-center text-sm text-muted">
            Made with ❤️ and ☕ by{" "}
            <a href="https://www.testmuai.com/" target="_blank" rel="noreferrer"
               className="text-clay hover:underline">TestMu AI</a>
          </div>
        </footer>
      </body>
    </html>
  );
}
