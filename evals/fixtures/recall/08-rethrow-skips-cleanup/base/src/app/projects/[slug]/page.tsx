import { ProjectSettings } from "./ProjectSettings";

export default async function ProjectPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ProjectSettings slug={slug} name={slug} />;
}
