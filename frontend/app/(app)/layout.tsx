import { AppLayout } from '@/components/layout/app-layout';

export default function AppLayoutWrapper({ children }: { children: React.ReactNode }) {
  return <AppLayout>{children}</AppLayout>;
}
