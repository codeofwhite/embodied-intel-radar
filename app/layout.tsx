import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "具身智能行业雷达",
  description: "面向具身智能求职、公司事件和机器人产业链行情的个人驾驶舱。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
