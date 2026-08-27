import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000',
  ),
  title: 'JobPilot · 智能求职工作台',
  description: '从简历解析到岗位匹配与投递管理，所有求职信息都在本地有序流转。',
  openGraph: {
    title: 'JobPilot · 智能求职工作台',
    description: '从简历解析到岗位匹配与投递管理，让求职流程清晰可控。',
    type: 'website',
    images: [{ url: '/og.png', width: 1672, height: 941, alt: 'JobPilot 智能求职工作台' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'JobPilot · 智能求职工作台',
    description: '从简历解析到岗位匹配与投递管理，让求职流程清晰可控。',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
