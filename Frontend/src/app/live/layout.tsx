export default function LiveLayout({ children }: LayoutProps<"/live">) {
  // No console chrome here: /live is a standalone full-screen theatre, entered
  // via ?case=<id> and exited back to /console by an explicit button.
  return <div className="min-h-dvh bg-[var(--bg)]">{children}</div>;
}
