"use server";

import { redirect } from "next/navigation";

type ProjectRef = { slug: string };

export async function renameProject(slug: string, name: string): Promise<void> {
  const renamed = await renameInStore(slug, name);
  if (renamed.slug !== slug) {
    redirect(`/projects/${renamed.slug}`);
  }
}

export async function duplicateProject(slug: string): Promise<void> {
  const copied = await copyInStore(slug);
  redirect(`/projects/${copied.slug}`);
}

async function renameInStore(slug: string, name: string): Promise<ProjectRef> {
  // ... 永続化。名前から slug を作り直して返す
  return { slug: name === slug ? slug : `${slug}-renamed` };
}

async function copyInStore(slug: string): Promise<ProjectRef> {
  // ... 永続化。複製先の slug を返す
  return { slug: `${slug}-copy` };
}
