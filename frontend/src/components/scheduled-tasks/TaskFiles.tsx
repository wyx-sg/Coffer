// src/components/scheduled-tasks/TaskFiles.tsx — an open task's Files tab: everything the task owns on disk.
//
// The same Files card a skill's folder is browsed in (SkillFileSplit, canvas
// 4.3.01), reaching the bottom of the window: the tree on the left, the open
// file on the right. The folder holds the task's PROMPT.md (open first, and the
// one file editable here) and whatever else belongs to the task — the scripts
// its prompt runs, intermediate files, the reports its runs write. Other files
// are changed on disk; Reveal in Finder opens the folder.
import { useState } from "react";

import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { SkillFileSplit } from "@/components/skills/SkillFileSplit";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useScheduledTaskFileContent, useScheduledTaskFiles } from "@/lib/hooks/useScheduledTasks";
import { PROMPT_FILE, TaskPromptFile } from "./TaskPromptFile";

function OpenFile({ uid, name, path }: { uid: string; name: string; path: string }) {
  const content = useScheduledTaskFileContent(uid, path);
  return <ReadOnlyFile path={path} displayPath={`${name}/${path}`} query={content} reveal />;
}

export function TaskFiles({ task }: { task: ScheduledTask }) {
  const tree = useScheduledTaskFiles(task.uid);
  const [selected, setSelected] = useState(PROMPT_FILE);
  return (
    <SkillFileSplit
      name={task.name}
      tree={tree}
      selected={selected}
      onSelect={setSelected}
      folderPath={task.folder}
      detail={
        selected === PROMPT_FILE ? (
          <TaskPromptFile task={task} />
        ) : (
          <OpenFile key={selected} uid={task.uid} name={task.name} path={selected} />
        )
      }
    />
  );
}
