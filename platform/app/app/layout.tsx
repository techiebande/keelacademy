import type { Metadata, Viewport } from "next";
import { Space_Grotesk, Inter, Fira_Mono } from "next/font/google";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { AuthProviders } from "@/components/auth/providers";
import { ThemeScript } from "@/components/theme-toggle";
import "./globals.css";

/*
  Goga is Modal's custom display face and not publicly available; Space
  Grotesk is the documented stand-in (geometric sans, squared terminals).
  Inter covers UI chrome with the 'cv11' variant; Fira Mono is the code
  window face. Variables feed the --font-goga / --font-inter-variable /
  --font-code-mono theme tokens in globals.css.
*/
const grotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-grotesk",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-inter-var",
  display: "swap",
});

const firaMono = Fira_Mono({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-fira-mono",
  display: "swap",
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: {
    default: "Keel Academy",
    template: "%s · Keel Academy",
  },
  description:
    "A project-based AI engineering program. Build one production system across 13 phases, with every submission graded against real tests and rubrics.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${grotesk.variable} ${inter.variable} ${firaMono.variable}`}
    >
      <head>
        <ThemeScript />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <AuthProviders>
          <SiteHeader />
          <main id="main">{children}</main>
          <SiteFooter />
        </AuthProviders>
      </body>
    </html>
  );
}
