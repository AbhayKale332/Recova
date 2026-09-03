import { ConsoleProvider } from "@/components/console/ConsoleContext";
import { ConsoleShell } from "@/components/console/ConsoleShell";

export default function ConsoleLayout({ children }: LayoutProps<"/console">) {
  return (
    <ConsoleProvider>
      <ConsoleShell>{children}</ConsoleShell>
    </ConsoleProvider>
  );
}
