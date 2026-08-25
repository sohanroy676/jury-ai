import SubmissionDetailView from "../../../components/SubmissionDetailView";

// Next 15 app-router dynamic pages receive `params` as a Promise; this
// server component awaits it and hands the id to the client view, which
// stays directly testable without router mocks.
export default async function SubmissionPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <SubmissionDetailView submissionId={id} />;
}
