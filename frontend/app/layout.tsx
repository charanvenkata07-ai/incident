import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from './providers';
import type { Metadata } from 'next';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'IncidentFlow',
  description: 'Enterprise incident assignment platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-zinc-50 dark:bg-zinc-950 font-sans antialiased text-zinc-900 dark:text-zinc-50">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
