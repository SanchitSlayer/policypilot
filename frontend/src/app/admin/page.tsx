import { ComingSoon, PageHeader } from "@/components/PageHeader";

export default function AdminPage() {
  return (
    <>
      <PageHeader title="Admin" description="Requests, tokens, latency and estimated cost per provider." />
      <ComingSoon phase={5} />
    </>
  );
}
