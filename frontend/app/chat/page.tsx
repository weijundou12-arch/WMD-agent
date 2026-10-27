import { Suspense } from "react";
import { ChatWorkspace } from "@/components/chat/chat-workspace";

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatWorkspace
        title="Agent Workspace"
        workspaceTitle="Auto Evidence Run"
        panelTitle="Evidence Review"
        initialMode="auto"
        examples={[
          "GLP-1 药物和骨密度之间有没有关系？",
          "德国司美格鲁肽目前多少钱？",
          "2025 年以后 RAG 在医疗 QA 里的最新进展是什么？"
        ]}
        plannedSteps={[
          "Intent routing",
          "Query planning",
          "Medical RAG or Web Search",
          "Evidence extraction",
          "Evidence Gate",
          "Cited answer"
        ]}
      />
    </Suspense>
  );
}
