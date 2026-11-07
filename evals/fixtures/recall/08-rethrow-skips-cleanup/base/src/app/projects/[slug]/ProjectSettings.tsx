"use client";

import { useState } from "react";
import { unstable_rethrow, useRouter } from "next/navigation";
import { useDialog } from "../../../components/DialogProvider";
import { showToast } from "../../../components/toast";
import { InputError, parseProjectName } from "../../../lib/projectName";
import { duplicateProject, renameProject } from "./actions";

export function ProjectSettings({ slug, name }: { slug: string; name: string }) {
  const { openDialog } = useDialog();

  async function handleDuplicate() {
    try {
      await duplicateProject(slug);
    } catch (err) {
      unstable_rethrow(err);
      showToast("複製できませんでした");
    }
  }

  return (
    <section>
      <h1>{name}</h1>
      <button type="button" onClick={() => openDialog(<RenameForm slug={slug} defaultName={name} />)}>
        名前を変更
      </button>
      <button type="button" onClick={handleDuplicate}>
        複製
      </button>
    </section>
  );
}

function RenameForm({ slug, defaultName }: { slug: string; defaultName: string }) {
  const { closeDialog } = useDialog();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);

  async function handleSubmit(formData: FormData) {
    setPending(true);
    setFieldError(null);
    try {
      const nextName = parseProjectName(formData.get("name"));
      await renameProject(slug, nextName);
    } catch (err) {
      if (err instanceof InputError) {
        setFieldError(err.message);
        return;
      }
      showToast("名前を変更できませんでした");
    } finally {
      setPending(false);
    }
    closeDialog();
    router.refresh();
  }

  return (
    <form action={handleSubmit}>
      <label>
        名前
        <input name="name" defaultValue={defaultName} disabled={pending} />
      </label>
      {fieldError && <p>{fieldError}</p>}
      <button type="submit" disabled={pending}>
        保存
      </button>
    </form>
  );
}
